import uuid
from email.policy import default
from typing import List

import sqlalchemy
from sqlalchemy import String, Integer, text, ForeignKey, select, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session, Mapped, relationship
from sqlalchemy.testing.schema import mapped_column, Table, Column

Base = declarative_base()

player_guild = Table(
    "player_guild",
    Base.metadata,
    Column("player_id", Integer, ForeignKey('player.id'), primary_key=True),
    Column("guild_id", Integer,  ForeignKey('guild.id'), primary_key=True),
)

player_quest = Table(
    "player_quest",
    Base.metadata,
    Column("player_id", Integer, ForeignKey('player.id'), primary_key=True),
    Column("quest_id", Integer, ForeignKey('quest.id'), primary_key=True),
)

class Player(Base):
    __tablename__ = "player"
    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    name = mapped_column(String, nullable=False)
    guilds: Mapped[List["Guild"]] = relationship(secondary=player_guild, back_populates="players", lazy="selectin")
    quests: Mapped[List["Quest"]] = relationship(secondary=player_quest, back_populates="players", lazy="selectin")


    def quest_completed(self):
        return len(self.quests)


    def __repr__(self) -> str:
        guild_count = len(self.guilds) if self.guilds else 0
        return f"Player(id={self.id!r}, name={self.name!r}, guilds={[x.name for x in self.guilds]}, quests={[x.name for x in self.quests]})"

class Guild(Base):
    __tablename__ = "guild"
    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    name = mapped_column(String, nullable=False)
    players: Mapped[List["Player"]] = relationship(secondary=player_guild, back_populates="guilds", lazy="selectin")

    def __repr__(self) -> str:
        player_count = len(self.players) if self.players else 0
        return f"Guild(id={self.id!r}, name={self.name!r}, guilds={player_count})"

class Quest(Base):
    __tablename__ = "quest"
    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    name = mapped_column(String, nullable=False)
    level_required = mapped_column(Integer, nullable=False)
    players: Mapped[List["Player"]] = relationship(secondary=player_quest, back_populates="quests", lazy="selectin")


class Item(Base):
    __tablename__ = "item"
    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    name = mapped_column(String, nullable=False)
    rarity = mapped_column(Integer, nullable=False, default=0) # 0 = common

# def takable_tasks(player_id, session: Session):
#     number = session.query(Player).filter(Player.id == player_id).first().quest_completed()
#     ans = session.query(Quest).filter(Quest.level_required <= number);
#     return [x.name for x in ans]

def takable_tasks(player_id, session: Session):
    completed_count = session.scalar(
        select(func.count(Quest.id))
        .join(player_quest, player_quest.c.quest_id == Quest.id)
        .where(player_quest.c.player_id == player_id)
    ) or 0

    stmt = (
        select(Quest)
        .where(Quest.level_required <= completed_count)
        .where(~Quest.players.any(Player.id == player_id))  # exclude completed
        .order_by(Quest.level_required)
    )

    quests = session.scalars(stmt).all()
    return [q.name for q in quests]

def seed_data(session: Session):
    # Players
    p1 = Player(name="Alice")
    p2 = Player(name="Bob")
    p3 = Player(name="Charlie")

    # Guilds
    g1 = Guild(name="Warriors")
    g2 = Guild(name="Mages")

    # Quests
    q1 = Quest(name="Slime Hunt", level_required=0)
    q2 = Quest(name="Goblin Fortress Raid", level_required=1)
    q3 = Quest(name="Dragon King’s Trial", level_required=2)

    # Items
    i1 = Item(name="Wooden Sword", rarity=0)
    i2 = Item(name="Magic Staff", rarity=1)
    i3 = Item(name="Legendary Dragon Blade", rarity=2)

    p1.guilds.append(g1)
    g1.players.append(p2)

    # NEW QUEST RELATIONSHIPS
    p1.quests.append(q1)
    p2.quests.append(q2)
    p3.quests.append(q3)

    session.add_all([p1, p2, p3, g1, g2, q1, q2, q3, i1, i2, i3])
    session.commit()

    print(p1)
    print(p2)
    print(p3)


def show_all_data(session):
    for table_name in Base.metadata.tables.keys():
        print(f"\n===== {table_name.upper()} =====")
        rows = session.execute(text(f"SELECT * FROM {table_name}")).fetchall()
        for row in rows:
            print(dict(row._mapping))




if __name__ == "__main__":
    engine = sqlalchemy.create_engine("sqlite:///:memory:", echo=False, future=True);

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_data(session)
        player_a = takable_tasks(1, session)
        print(player_a)
        # show_all_data(session)



# 🎮 Game World Relational Challenge
#
# You’re building a multiplayer fantasy RPG database with these tables:
#
# Player(id, name)
# Guild(id, name)
# Quest(id, name, level_required)
# Item(id, name, rarity)  -- rarity: common, rare, epic
#
# PlayerGuild(player_id → Player.id, guild_id → Guild.id)
# PlayerQuest(player_id → Player.id, quest_id → Quest.id, completed: boolean)
# GuildItem(guild_id → Guild.id, item_id → Item.id)
#
# 💥 Missions (query challenges)
# 1️⃣ Quest Eligibility
#
# Write a SQL query to list all quests a player can accept given:
#
# player_id = :pid
#
# player can accept quests where level_required <= their number of completed quests
# (Yes, completing quests increases your “level”)
#
# Output:
#
# quest.id, quest.name
#
# ✨ This requires joining + aggregation + filtering quests they haven’t already completed.