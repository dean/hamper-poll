from collections import defaultdict
import datetime
import re
import time

from hamper.interfaces import ChatCommandPlugin, Command
from hamper.utils import ude

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base

from twisted.internet import reactor

SQLAlchemyBase = declarative_base()


class Poll(ChatCommandPlugin):
    """ Vote on polls. """

    name = 'poll'

    priority = 1

    short_desc = 'poll - Start and vote on polls.'
    long_desc = ('!poll <topic> <duration> - Start a poll with a given <topic>'
                 ' that lasts <duration> (minutes).\n'
                 '!vote <topic> <choice> - Vote on a <topic> with <choice>.')

    def setup(self, loader):
        super(Poll, self).setup(loader)
        self.db = loader.db
        SQLAlchemyBase.metadata.create_all(self.db.engine)

    def close_poll(self, bot, comm, poll_id):
        """
        Closes the current Poll.
        """
        poll = self.db.session.query(PollTable).filter_by(id=poll_id).first()

        # Get all the votes. This could probably be done better without
        # defaultdict, but I'm in a time crunch :p
        db_votes = self.db.session.query(Vote).filter(
                        Vote.poll_id == poll_id
                    ).all()

        votes = defaultdict(int)
        for vote in db_votes:
            votes[vote.option] += 1

        # Sorts by the number of votes on a given option
        # Reverse so we go highest to lowest.
        options = list(reversed(sorted(votes.items(), key=lambda x: x[1])))
        num_options = 5 if len(options) > 5 else len(options)

        option_and_vote = '{:^20} | {:^8}'

        # Generate the reply string
        bot.reply(comm, 'The poll for \'{0}\' is over! And the results '
                        'are:'.format(poll.topic))
        bot.reply(comm, '{:^20}   {:^8}'.format('Option', 'Votes'))
        bot.reply(comm, '_______________________________')
        for x in xrange(num_options):
            bot.reply(comm, option_and_vote.format(
                        options[x][0], options[x][1]))

        # Remove that poll so it can be re-voted in the future
        self.db.session.delete(poll)

        # Remove votes; we don't need them anymore.
        for vote in db_votes:
            self.db.session.delete(vote)

        self.db.session.commit()

    def existing_poll(self, topic):
            return self.db.session.query(PollTable).filter_by(
                                                        topic=topic
                                                    ).first()

    class StartPoll(Command):
        name = 'pizza'
        regex = r'^poll "(.+)" "(.+)"$'

        short_desc = ('!poll <topic> <duration> - Start a poll with a given '
                      '<topic> to last <duration> in minutes')

        def command(self, bot, comm, groups):
            if len(groups) != 2:
                return bot.reply(comm, "Not enough arguments provided...")

            topic = groups[0]

            if self.plugin.existing_poll(topic):
                return bot.reply(comm, "A poll with that topic already "
                                 "exists!")

            # reactor.callLater takes it's arguments as floats.
            duration = float(groups[1])

            db = self.plugin.db

            new_poll = PollTable(topic=topic, duration=duration)
            db.session.add(new_poll)
            db.session.commit()

            args = (bot, comm, new_poll.id)
            reactor.callLater(duration * 60, self.plugin.close_poll, *args)

            # Make the duration more readable.
            duration = str(int(duration))

            bot.reply(comm, "{0} has initiated a poll for {1} that lasts {2} "
                      "minutes!".format(comm['user'], topic, duration))

    class Vote(Command):
        name = 'vote'
        regex = r'^vote \"(.+)\" \"(.+)\"$'

        short_desc = ('!vote <topic> <option> - Vote <option> on <topic>.')

        def command(self, bot, comm, groups):
            if len(groups) != 2:
                return bot.reply(comm, "Not enough arguments provided...")

            existing_poll = self.plugin.existing_poll(groups[0])

            if not existing_poll:
                return bot.reply(comm, '{0}, there is no poll for \'{1}\' '
                                 'right now!'.format(comm['user'], groups[0]))

            prev_vote = self.plugin.db.session.query(Vote).filter(
                            Vote.user == comm['user'],
                            Vote.poll_id == existing_poll.id
                        ).first()

            if prev_vote:
                self.plugin.db.session.delete(prev_vote)
                self.plugin.db.session.commit()

            vote = Vote(comm['user'], groups[1], existing_poll.id)

            self.plugin.db.session.add(vote)
            self.plugin.db.session.commit()

            bot.reply(comm, '{0}, your vote for \'{1}\' has been '
                        'cast!'.format(comm['user'], groups[0]))


class PollTable(SQLAlchemyBase):
    """
    Stsrt a pizza poll for a certain duration.
    """

    __tablename__ = 'polls'

    id = Column(Integer, primary_key=True)
    topic = Column(String(1024))
    endtime = Column(DateTime)

    def __init__(self, topic, duration=10):
        self.topic = topic
        self.endtime = self.calculate_end(duration)

    def calculate_end(self, duration):
        return datetime.datetime.now() + datetime.timedelta(minutes=duration)


class Vote(SQLAlchemyBase):
    """
    A vote for a single player on which pizza to get.
    """

    __tablename__ = 'votes'

    id = Column(Integer, primary_key=True)
    user = Column(String)
    option = Column(String)
    poll_id = Column(Integer)  # I'll add a FK to this later.

    def __init__(self, user, option, poll_id):
        self.user = user
        self.option = option
        self.poll_id = poll_id

poll = Poll()
