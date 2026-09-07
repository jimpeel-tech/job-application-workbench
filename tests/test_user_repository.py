from pathlib import Path

import pytest

from jaw.persistence.user_repository import UserRepository


def initialized_repository(path: Path) -> UserRepository:
    repository = UserRepository(path)
    with repository.transaction() as session:
        session.initialize_schema()
    return repository


def test_user_repository_round_trips_accounts_and_preferences(
    tmp_path: Path,
) -> None:
    repository = initialized_repository(tmp_path / "data" / "jaw.db")

    with repository.transaction() as session:
        first_id = session.create_user(
            "Zoë",
            {"user": {"first_name": "Zoë"}, "tags": ["SRE"]},
        )
        second_id = session.create_user("alpha", {"user": {}})
        session.set_preference("active_user_id", str(second_id))

    with repository.transaction() as session:
        account = session.get_user(first_id)
        assert account is not None
        assert account.name == "Zoë"
        assert account.data == {
            "user": {"first_name": "Zoë"},
            "tags": ["SRE"],
        }
        assert session.active_user_id() == second_id
        assert [item.name for item in session.list_users()] == ["alpha", "Zoë"]


def test_user_repository_rolls_back_failed_transaction(tmp_path: Path) -> None:
    repository = initialized_repository(tmp_path / "jaw.db")

    with pytest.raises(RuntimeError, match="abort"):
        with repository.transaction() as session:
            session.create_user("Temporary", {"value": "not committed"})
            session.set_preference("active_user_id", "1")
            raise RuntimeError("abort")

    with repository.transaction() as session:
        assert session.count_users() == 0
        assert session.get_preference("active_user_id") is None


def test_user_repository_uses_first_account_without_active_preference(
    tmp_path: Path,
) -> None:
    repository = initialized_repository(tmp_path / "jaw.db")

    with repository.transaction() as session:
        first_id = session.create_user("First", {"value": 1})
        session.create_user("Second", {"value": 2})

    with repository.transaction() as session:
        assert session.active_user_id() == first_id
