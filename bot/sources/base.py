import re
import time
from dataclasses import dataclass, field

# Chỉ những từ thể hiện rõ là chương trình bán hàng (tránh nhầm "giá vàng giảm 1%" là sale)
SALE_WORDS = re.compile(
    r"\bsale\b|khuyến mãi|khuyến mại|voucher|mã giảm|freeship|flash ?sale|\bdeal\b|ưu đãi|xả kho|"
    r"đồng giá|săn sale|giảm (?:đến|tới|sốc)|siêu sale|mua 1 tặng 1|hoàn tiền",
    re.I,
)


def is_sale(text: str) -> bool:
    return bool(SALE_WORDS.search(text))


@dataclass
class Item:
    title: str
    url: str
    source: str
    text: str = ""
    kind: str = "hot"  # hot | sale
    published: float = field(default_factory=time.time)
    engagement: int = 0  # like/reply/repost nếu có

    def __post_init__(self):
        if self.kind == "hot" and is_sale(f"{self.title} {self.text}"):
            self.kind = "sale"

    def score(self) -> float:
        age_h = max(0.0, (time.time() - self.published) / 3600)
        return self.engagement ** 0.5 + 10 / (1 + age_h)
