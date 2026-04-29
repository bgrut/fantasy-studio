from .city_loop import build_city_loop
from .product_pedestal import build_product_pedestal
from .neon_news import build_neon_news

TEMPLATE_BUILDERS = {
    "city_loop": build_city_loop,
    "product_pedestal": build_product_pedestal,
    "neon_news": build_neon_news,
}
