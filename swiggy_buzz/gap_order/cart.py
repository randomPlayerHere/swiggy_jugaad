from swiggy_buzz import config

from .models import CartLine


def cart_total(lines: list[CartLine]) -> float:
    return sum(line.price * line.qty for line in lines)


def apply_cap(
    lines: list[CartLine], cap_inr: float = config.CART_CAP_INR
) -> tuple[list[CartLine], list[CartLine]]:
    """Cheapest-first greedy fill: keep adding the next-cheapest line while it
    still fits under cap_inr, drop everything that would push the total over.
    Maximizes how many ingredients make it into the basket, at the cost of
    possibly dropping one expensive-but-needed item.
    """
    kept: list[CartLine] = []
    dropped: list[CartLine] = []
    running_total = 0.0

    for line in sorted(lines, key=lambda line: line.price):
        line_total = line.price * line.qty
        if running_total + line_total <= cap_inr:
            kept.append(line)
            running_total += line_total
        else:
            dropped.append(line)

    return kept, dropped