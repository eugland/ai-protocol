import uuid
from typing import List

from sqlalchemy import Table, Column, Integer, String, MetaData, create_engine, ForeignKey, UUID, select
from sqlalchemy.orm import mapper, DeclarativeBase, Mapped, relationship, Session
from sqlalchemy.testing.schema import mapped_column


class Base(DeclarativeBase):
    pass


user_group_table = Table(
    'user_group',
    Base.metadata,
    Column('user_id', UUID, ForeignKey('user.id'), primary_key=True),
    Column('group_id', UUID, ForeignKey('group.id'), primary_key=True)
)

group_permission_table = Table(
    'group_permission',
    Base.metadata,
    Column('group_id', UUID, ForeignKey('group.id'), primary_key=True),
    Column('permission_id', UUID, ForeignKey('permission.id'), primary_key=True)
)

class User(Base):
    __tablename__ = 'user'

    def __init__(self, Name: str = None, **kwargs):
        super().__init__(**kwargs)
        if Name is not None:
            self.Name = Name

    id = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    email = mapped_column(String, unique=True, index=True)
    name = mapped_column(String, nullable=False)
    groups: Mapped[List["Group"]] = relationship(secondary=user_group_table, back_populates="users", lazy="selectin")

    @property
    def Name(self):
        return self.name

    @Name.setter
    def Name(self, value):
        self.name = value
        self.email = f"{value.lower()}@gmail.com"

    def has_permission(self, name: str) -> bool:
        """In-memory check if user has a given permission name."""
        return any(
            perm.name == name
            for group in self.groups
            for perm in group.permissions
        )

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, name={self.name!r}, email={self.email!r})"


class Group(Base):
    __tablename__ = 'group'
    id = mapped_column( UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = mapped_column(String, nullable=False, unique=True)
    users: Mapped[List[User]] = relationship(secondary=user_group_table, back_populates="groups", lazy="selectin")
    permissions: Mapped[List["Permission"]] = relationship(secondary=group_permission_table, back_populates="groups", lazy="selectin")

class Permission(Base):
    __tablename__ = 'permission'
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = mapped_column(String, nullable=False, unique=True)

    groups: Mapped[List["Group"]] = relationship(
        secondary=group_permission_table, back_populates="permissions", lazy="selectin"
    )


def seed_data(session: Session) -> None:
    # permissions
    p_admin = Permission(name="admin")
    p_editor = Permission(name="editor")
    p_viewer = Permission(name="viewer")

    # groups
    g_admins = Group(name="admins", permissions=[p_admin])
    g_staff = Group(name="staff", permissions=[p_editor, p_viewer])
    g_readonly = Group(name="readonly", permissions=[p_viewer])

    # users
    u_alice = User(Name="alice", groups=[g_admins])               # admin
    u_bob = User(Name="bob", groups=[g_staff])                    # editor + viewer
    u_charlie = User(Name="charlie", groups=[g_readonly])         # viewer only
    u_dana = User(Name="dana")                                    # no groups

    session.add_all([
        p_admin, p_editor, p_viewer,
        g_admins, g_staff, g_readonly,
        u_alice, u_bob, u_charlie, u_dana,
    ])
    session.commit()


def test_in_memory_checks(session: Session) -> None:
    users = session.scalars(select(User).order_by(User.email)).all()
    for u in users:
        print(
            u.email,
            "admin:", u.has_permission("admin"),
            "editor:", u.has_permission("editor"),
            "viewer:", u.has_permission("viewer"),
        )


def test_sql_level_check(session: Session) -> None:
    # Example: all users who have 'admin' permission through any group
    stmt = (
        select(User)
        .join(User.groups)
        .join(Group.permissions)
        .where(Permission.name == "admin")
        .distinct()
    )
    admins = session.scalars(stmt).all()
    print("Users with 'admin' permission via group:", admins)


if __name__ == "__main__":
    engine = create_engine("sqlite:///:memory:", echo=False, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_data(session)
        print("=== In-memory has_permission() checks ===")
        test_in_memory_checks(session)
        print("\n=== SQL-level join/select test ===")
        test_sql_level_check(session)



