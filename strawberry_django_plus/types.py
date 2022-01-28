import enum
import inspect
from typing import (
    TYPE_CHECKING,
    Callable,
    Iterable,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
)

from django.db.models.fields import Field
from django.db.models.fields.reverse_related import ForeignObjectRel
import strawberry
from strawberry.custom_scalar import ScalarWrapper
from strawberry.type import StrawberryType
from strawberry_django.fields.types import (
    resolve_model_field_type as _resolve_model_field,
)
from strawberry_django.fields.types import field_type_map

from .utils.typing import TypeOrIterable

if TYPE_CHECKING:
    from strawberry_django_plus.type import StrawberryDjangoType

try:
    from django_choices_field import IntegerChoicesField, TextChoicesField
except ImportError:
    has_choices_field = False
else:
    has_choices_field = True


_T = TypeVar("_T", bound=Union[StrawberryType, ScalarWrapper])


def register(
    fields: TypeOrIterable[Type[Field]],
    /,
    *,
    for_input: bool = False,
) -> Callable[[_T], _T]:
    """Register types to convert `auto` fields to.

    Args:
        field:
            Type or sequence of types to register
        for_input:
            If the type should be used for input only.

    Examples:
        To define a type that should be used for `ImageField`:

        >>> @register(ImageField)
        ... @strawberry.type
        ... class SomeType:
        ...     url: str

    """

    def _wrapper(type_):
        for f in fields if isinstance(fields, Iterable) else [fields]:
            field_type_map[f] = type_

        return type_

    return _wrapper


def resolve_model_field_type(
    model_field: Union[Field, ForeignObjectRel],
    django_type: "StrawberryDjangoType",
):
    """Resolve type for model field."""
    if has_choices_field and isinstance(model_field, (TextChoicesField, IntegerChoicesField)):
        field_type = model_field.choices_enum
        enum_def = getattr(field_type, "_enum_definition", None)
        if enum_def is None:
            doc = field_type.__doc__ and inspect.cleandoc(field_type.__doc__)
            enum_def = strawberry.enum(field_type, description=doc)._enum_definition
        return enum_def

    return _resolve_model_field(model_field, django_type)


@strawberry.type
class OperationMessage:
    """An error that happened while executing an operation."""

    @strawberry.enum(name="OperationMessageKind")
    class Kind(enum.Enum):
        """The kind of the returned message."""

        INFO = "info"
        WARNING = "warning"
        ERROR = "error"
        PERMISSION = "permission"
        VALIDATION = "validation"

    kind: Kind = strawberry.field(description="The kind of this message.")
    message: str = strawberry.field(description="The error message.")
    field: Optional[str] = strawberry.field(
        description=(
            "The field that caused the error, or `null` if it "
            "isn't associated with any particular field."
        ),
        default=None,
    )


@strawberry.type
class OperationMessages:
    """Multiple messages returned by an operation."""

    messages: List[OperationMessage] = strawberry.field(
        description="List of messages returned by the operation.",
    )
