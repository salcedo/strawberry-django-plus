# strawberry-django-plus

[![build status](https://img.shields.io/endpoint.svg?url=https%3A%2F%2Factions-badge.atrox.dev%2Fblb-ventures%2Fstrawberry-django-plus%2Fbadge%3Fref%3Dmaster&style=flat)](https://actions-badge.atrox.dev/blb-ventures/straw/goto?ref=master)
[![coverage](https://img.shields.io/codecov/c/github/blb-ventures/strawberry-django-plus.svg)](https://codecov.io/gh/blb-ventures/strawberry-django-plus)
[![PyPI version](https://img.shields.io/pypi/v/strawberry-django-plus.svg)](https://pypi.org/project/strawberry-django-plus/)
![python version](https://img.shields.io/pypi/pyversions/strawberry-django-plus.svg)
![django version](https://img.shields.io/pypi/djversions/strawberry-django-plus.svg)

Enhanced Strawberry integration with Django.

Built on top of [strawberry-django](https://github.com/strawberry-graphql/strawberry-graphql-django)
integration, enhancing its overall functionality.

## Features

- All of supported features by `strawberry-django`.
- Extension that [automatically optimize queries](#automatic-queryset-optimization) (using
  `only`/`select_related`/`prefetch_related`) to solve graphql `N+1` problems, with support for
  fragment spread, inline fragments, `@include`/`@skip` directives, prefetch merging, etc
- Improved sync/async resolver that priorizes the model's cache to avoid have to use
  [sync_to_async](https://docs.djangoproject.com/en/4.0/topics/async/#asgiref.sync.sync_to_async)
  when not needed.
- Support for [Django choices enums using](#django-choices-enums) (requires
  [django-choices-field](https://github.com/bellini666/django-choices-field))
- [Permissioning](#permissioning) using schema directives with the default
  [django authentication system](https://docs.djangoproject.com/en/4.0/topics/auth/default/),
  with support for both direct and per-object permission checking for backends that
  support those (e.g. [django-guardian](https://django-guardian.readthedocs.io/en/stable])).
- [Relay support](#relay-support) for queries, connections and input mutations.
- [Django Debug Toolbar integration](#django-debug-toolbar-integration) with graphiql to
  display metrics like SQL queries
- (Coming Soon...) Improved Django mutations with automatic validation errors integration.
- A well typed and documented API.

## Installation

Install it with pip:

```shell
pip install strawberry-django-plus
```

## Introduction

Since this lib has a long name, it does provide a shortcut called `gql` where all of
strawberry's API and ours can be accessed.

```python
from strawberry_django_plus import gql

# All strawberry's base api can be found directly on gql, like:
gql.type  # same as strawberry.type
gql.field  # same as strawberry.field
...

# The strawberry-django API and our custom implementation can be found on gql.django, like:
gql.django.type
gql.django.field
...

# We also have a custom relay implementation in here:
gql.relay
```

## How To

### Automatic QuerySet Optimization

The automatic optimization is enabled by adding the `DjangoOptimizerExtension` to your
strawberry's schema config.

```python
import strawberry
from strawberry_django_plus.optimizer import DjangoOptimizerExtension

schema = strawberry.Schema(
    Query,
    extensions=[
        # other extensions...
        DjangoOptimizerExtension,
    ]
)
```

Now consider the following:

```python
# models.py

class Artist(models.Model):
    name = models.CharField()

class Album(models.Moodel):
    name = models.CharField()
    release_date = models.DateTimeField()
    artist = models.ForeignKey("Artist", related_name="albuns")

class Song(models.Model):
    name = model.CharField()
    duration = models.DecimalField()
    album = models.ForeignKey("Album", related_name="songs")

# schema.py
from strawberry_django_plus import gql

@gql.django.type(Artist)
class ArtistType:
    name: auto
    albums: "List[AlbumType]"

@gql.django.type(Album)
class AlbumType:
    name: auto
    release_date: auto
    artist: ArtistType
    songs: "List[SongType]"

@gql.django.type(Song)
class SongType:
    name: auto
    duration: auto
    album_type: AlbumType

@gql.type
class Query:
    artist: Artist = gql.django.field()
    songs: List[SongType] = gql.django.field()
```

Querying the artist field:

```gql
{
  artist {
    id
    name
    albums {
      id
      name
      songs {
        id
        name
      }
    }
  }
}
```

```python
# This will generate a query like:
Artist.objects.all().only("id", "name").prefetch_related(
    Prefetch(
        "albums",
        queryset=Album.objects.all().only("id", "name").prefetch_related(
            "songs",
            Song.objects.all().only("id", "name"),
        )
    ),
)
```

And querying the songs list:

```gql
{
  song {
    id
    album
    id
    name
    artist {
      id
      name
      albums {
        id
        name
        release_date
      }
    }
  }
}
```

```python
# This will generate a query like:
Song.objects.all().only(
    "id",
    "album",
    "album__id",
    "album__name",
    "album__release_date",  # Note about this below
    "album__artist",
    "album__artist__id",
).select_related(
    "album",
    "album__artist",
).prefetch_related(
    "album__artist__albums",
    Prefetch(
        "albums",
        Album.objects.all().only("id", "name", "release_date"),
    )
)
```

Note that even though `album__release_date` field was not selected here, it got selected
in the prefetch query later. Since Django caches known objects, we have to select it here or
else it would trigger extra queries latter.

It is also possible to include hints for non-model fields using the field api or even our
`@model_property` (or its cached variation, `@cached_model_property`) decorator on the model
itself, for people who likes to keep all the business logic at the model.

For example, the following will automatically optimize `only` and `select_related` if that
field gets selected:

```python
from strawberry_django_plus import gql

class Song(models.Model):
    name = models.CharField()

    @gql.model_property(only=["name", "album__name"], select_related=["album"])
    def name_with_album(self) -> List[str]:
        return f"{self.album.name}: {self.name}"

@gql.django.type(Song)
class SongType:
    name: auto
    name_with_album: str
```

Another option would be to define that on the field itself:

```python
@gql.django.type(Song)
class SongType:
    name: auto
    name_with_album: str = gql.django.field(
        only=["name", "album__name"],
        select_related=["album"],
    )
```

### Django Choices Enums

Convert choices fields into GraphQL enums by using
[Django Choices Field](https://github.com/bellini666/django-choices-field) extension.

```python
from django_choices_field import TexChoicesField

class Song(models.Model):
    class Genre(models.TextChoices):
        ROCK = "rock", "Rock'n'Roll"
        METAL = "metal", "Metal"
        OTHERS = "others", "Who Cares?"

    genre = TextChoicesField(choices_enum=Genre)
```

In that example, a new enum called `Genre` will be created and be used for queries
and mutations.

If you want to name it differently, decorate the class with `@gql.enum` with your preferred
name so that strawberry-django-plus will not try to register it again.

### Permissioning

Permissioning is done using schema directives by applying them to the fields that requires
permission checking.

For example:

```python
@strawberry.type
class SomeType:
    login_required_field: RetType = strawberry.field(directives=[LoginRequired()])
    perm_required_field: OtherType = strawberry.field(
        directives=[PermRequired("some_app.some_perm")],
    )
    obj_perm_required_field: OtherType = strawberry.field(
        directives=[ObjPermRequired("some_app.some_perm")],
    )
```

- `login_required_field` will check if the user is authenticated
- `perm_required_field` will check if the user has `"some_app.some_perm"` permission
- `obj_perm_required_field` will check the permission for the resolved value

Available options are:

- `LoginRequired`: Checks if the user is authenticated (`user.is_autenticated`)
- `StaffRequired`: Checks if the user is a staff member (`user.is_staff`)
- `SuperuserRequired`: Checks if the user is a superuser (`user.is_superuser`)
- `PermRequired(perms: str, list[str], any: bool = True)`: Checks if the user has any or all of
  the given permissions (`user.has_perm(perm)`)
- `RootPermRequired(perms: str | list[str], any: bool = True)`: Checks if the user has any or all
  of the given permissions for the root of that field (`user.has_perm(perm, root)`)
- `ObjPermRequired(perms: str | list[str], any: bool = True)`: Resolves the retval and then
  checks if the user has any or all of the given permissions for that specific value
  (`user.has_perm(perm, retval)`). Note that if the return value is a list, this directive
  will filter the return value, removing objects that fails the check (check below for more
  information regarding other possibilities).

There are some important notes regarding how the directives handle the return value:

- If the user passes the check, the retval is returned normally
- If the user fails the check:
  - If the return type was `Optional`, it returns `None`
  - If the return type was a `List`, it returns an empty list
  - If the return type was a relay `Connection`, it returns an empty `Connection`
  - Otherwise, it raises a `PermissionError` for that resolver

Note that since `strawberry` doesn't support resolvers for schema directives, it is necessary
to use this lib's custom extension that handles the resolution of those and any other custom
defined schema directive inherited from `strawberry_django_plus.directives.SchemaDirectiveResolver`:

```python
import strawberry
from strawberry_django_plus.directives import SchemaDirectiveExtension

schema = strawberry.Schema(
    Query,
    extensions=[
        SchemaDirectiveExtension,
        # other extensions...
    ]
)
```

### Relay Support

We have a custom [relay spec](https://relay.dev/docs/guides/graphql-server-specification/)
implementation. It is not tied to Django at all to allow its usage with other types.

It provides types and fields for node and connection querying. For example:

```python
# schema.py
from strawberry_django_plus import gql
from strawberry_django_plus.gql import relay

@gql.type
class Fruit(relay.Node):
    name: str

    def resolve_node(cls, node_id, info, required=False):
        ...

    def resolve_nodes(cls, node_id, info, node_ids=False):
        ...


@gql.type
class Query:
    fruit: Optional[Fruit] = relay.node()
    fruits_connection: relay.Connection[Fruit] = relay.connection()

    @relay.connection
    def fruits_connection_filtered(self, name_startswith: str) -> Iterable[Fruit]:
        # Note that this resolver is special. It should not resolve the connection, but
        # the iterable of nodes itself. Thus, any arguments defined here will be appended
        # to the query, and the pagination of the iterable returned here will be
        # automatically handled.
        ...
```

This will generate a schema like this:

```gql
interface Node {
  id: GlobalID!
}

type Fruit implements Node {
  id: GlobalID!
  name: String!
}

type FruitEdge implements Node {
  cursor: String!
  node: Fruit
}

type FruitConnection {
  edges: [ShipEdge!]!
  pageInfo: PageInfo!
}

type PageInfo {
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
  startCursor: String
  endCursor: String
}

type Query {
  fruit(id: GlobalID!): Fruit
  fruits_connection(
    before: String
    after: String
    first: Int
    last: Int
  ): FruitConnection
  fruits_connection_filtered(
    before: String
    after: String
    first: Int
    last: Int
    nameStartswith: String!
  ): FruitConnection
}
```

It is expected that types implementing the `Node` interface define some methods, like
`resolve_nodes` and `resolve_node`. Take a look at
[the documentation](.strawberry_django_plus.relay.py) for more information.

Also note that Django fields created with `@gql.django.type` automatically implements
all of the required methods when the type inherits from `Node`.

This module also exposes a mutation that converts all of its arguments to a single input.
For example:

```python
@gql.type
class Mutation:
    @relay.input_mutation
    def create_fruit(name: str) -> Fruit:
        ....
```

Will generate those types:

```gql
input CreateFruitInput {
  name: String!
}

type Mutation {
  createFruit(input: CreateFruitInput!): Fruit
}
```

### Django Debug Toolbar Integration

Install [Django Debug Toolbar](https://github.com/jazzband/django-debug-toolbar)
and change its middleware from:

```python
MIDDLEWARE = [
    ...
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    ...
]
```

To:

```python
MIDDLEWARE = [
    ...
    "strawberry_django_plus.middlewares.debug_toolbar.DebugToolbarMiddleware",
    ...
]
```

## Contributing

We use [poetry](https://github.com/sdispater/poetry) to manage dependencies, to
get started follow these steps:

```shell
git clone https://github.com/blb-ventures/strawberry-django-plus
cd strawberry
poetry install
poetry run pytest
```

This will install all the dependencies (including dev ones) and run the tests.

### Pre commit

We have a configuration for
[pre-commit](https://github.com/pre-commit/pre-commit), to add the hook run the
following command:

```shell
pre-commit install
```

## Licensing

The code in this project is licensed under MIT license. See [LICENSE](./LICENSE)
for more information.
