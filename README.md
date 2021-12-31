# Chatter

Chatter is a work-in-progress chat server and webapp based on the [Django Channels tutorial](https://channels.readthedocs.io/en/stable/tutorial/index.html). Users will be able to create chatrooms with three types of access:

- Public - accessible to anyone with the room number.
- Confirmed only - accessible to any user with the room number and a confirmed email address.
- Private - accessible to invited users only.

## Requirements and Installation

To set up Bookmarker, the following need to be installed:

- Python 3.9.
- A Postgres server.
- A Redis server.

To install the Python requirements for Chatter, run `pip install -r requirements.txt`.

Chatter also requires the following environment variables to be set (except where a default value is specified):

- DJANGO_SECRET_KEY (Secret key for Django.)
- DEBUG (Default is False.)
- DB_HOST (Hostname of Postgres server. Default is 127.0.0.1.)
- DB_PORT (Port of Postgres server. Default is 5432.)
- DB_USER (Postgres username.)
- DB_PASSWORD (Postgres password.)
- DB_NAME (Postgres database name.)
- REDIS_HOST (Hostname of Redis server. Default is 127.0.0.1.)
- REDIS_PORT (Port of Redis server. Default is 6379.)

## Contributing

Before making any changes, please install the development dependencies and pre-commit hooks by running the commands below:

```
pip install -r requirements-dev.txt
pre-commit install
```

The pre-commit hooks (Black and Prettier) help to ensure that the style of the code is consistent.
