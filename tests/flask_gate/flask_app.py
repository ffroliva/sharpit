from __future__ import annotations

from flask import Flask, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ForeignKey, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

db = SQLAlchemy()


class Author(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    books: Mapped[list[Book]] = relationship(lazy="select", back_populates="author")


class Book(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("author.id"))
    author: Mapped[Author] = relationship(back_populates="books")


def create_app(fixed: bool = False) -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    db.init_app(app)
    with app.app_context():
        db.create_all()
        db.session.add_all(Author(books=[Book(), Book()]) for _ in range(6))
        db.session.commit()

    @app.get("/authors")
    def authors() -> Response:
        query = select(Author)
        if fixed:
            query = query.options(selectinload(Author.books))
        return jsonify([{"books": [book.id for book in author.books]} for author in db.session.scalars(query)])

    return app
