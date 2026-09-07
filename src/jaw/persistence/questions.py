from __future__ import annotations

from .types import ConnectionFactory


class QuestionRepository:
    """Persistence operations for application questions and answers."""

    def __init__(self, connect: ConnectionFactory) -> None:
        self._connect = connect

    def add_question(
        self,
        job_id: int,
        question: str,
        suggested_answer: str = "",
        submitted_answer: str = "",
    ) -> int:
        question = str(question).strip()
        if not question:
            raise ValueError("Question is required")
        submitted_answer = str(submitted_answer)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO questions(
                    job_id,question,suggested_answer,submitted_answer,submitted_at
                ) VALUES (?,?,?,?,CASE WHEN ? <> '' THEN CURRENT_TIMESTAMP ELSE NULL END)
                """,
                (job_id, question, suggested_answer, submitted_answer, submitted_answer),
            )
            connection.execute(
                "UPDATE jobs SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (job_id,),
            )
            return int(cursor.lastrowid)

    def update_question(
        self,
        job_id: int,
        question_id: int,
        question: str,
        answer: str,
    ) -> bool:
        question = str(question).strip()
        if not question:
            raise ValueError("Question is required")
        answer = str(answer)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE questions
                SET question=?,submitted_answer=?,
                    submitted_at=CASE
                        WHEN ? <> '' THEN COALESCE(submitted_at,CURRENT_TIMESTAMP)
                        ELSE NULL
                    END
                WHERE id=? AND job_id=?
                """,
                (question, answer, answer, question_id, job_id),
            )
            if cursor.rowcount:
                connection.execute(
                    "UPDATE jobs SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (job_id,),
                )
            return bool(cursor.rowcount)

    def delete_question(self, job_id: int, question_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM questions WHERE id=? AND job_id=?",
                (question_id, job_id),
            )
            if cursor.rowcount:
                connection.execute(
                    "UPDATE jobs SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (job_id,),
                )
            return bool(cursor.rowcount)

    def submit_answer(self, question_id: int, answer: str) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT job_id FROM questions WHERE id=?",
                (question_id,),
            ).fetchone()
            connection.execute(
                """
                UPDATE questions
                SET submitted_answer=?,
                    submitted_at=CASE WHEN ? <> '' THEN CURRENT_TIMESTAMP ELSE NULL END
                WHERE id=?
                """,
                (answer, answer, question_id),
            )
            if row is not None:
                connection.execute(
                    "UPDATE jobs SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (int(row["job_id"]),),
                )
