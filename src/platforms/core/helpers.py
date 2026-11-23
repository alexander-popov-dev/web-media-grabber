from collections.abc import Iterator
from typing import Any


def iter_by_marker_key(
    obj: Any,
    marker_key: str,
    *,
    return_parent_dict: bool = False,
    path: str = "",
) -> Iterator[tuple[str, dict[str, Any]]]:
    """
    Ищет словари на любой глубине, содержащие `marker_key`.

    - return_parent_dict=False: вернет значение `d[marker_key]` (если оно dict).
    - return_parent_dict=True: вернет сам словарь `d`, внутри которого лежит `marker_key`.
    """
    if isinstance(obj, dict):
        if marker_key in obj:
            target = obj if return_parent_dict else obj[marker_key]
            if isinstance(target, dict):
                yield path or "<root>", target

        for k, v in obj.items():
            next_path = f"{path}.{k}" if path else str(k)
            yield from iter_by_marker_key(
                v,
                marker_key,
                return_parent_dict=return_parent_dict,
                path=next_path,
            )

    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            next_path = f"{path}[{idx}]"
            yield from iter_by_marker_key(
                item,
                marker_key,
                return_parent_dict=return_parent_dict,
                path=next_path,
            )


def get_dict_by_marker_key(
    obj: Any,
    marker_key: str,
    *,
    return_parent_dict: bool = False,
) -> dict[str, Any] | None:
    """Возвращает первый найденный словарь по уникальному ключу-маркеру или None."""
    match = next(
        iter_by_marker_key(obj, marker_key, return_parent_dict=return_parent_dict),
        None,
    )
    if match is None:
        return None
    _, found_dict = match
    return found_dict