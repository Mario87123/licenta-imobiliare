from .crawler_olx import run_olx_crawler
from .crawler_storia import run_storia_crawler
from .crawler_imobiliare import run_imobiliare_crawler


CRAWLER_REGISTRY = {
    "olx": run_olx_crawler,
    "storia": run_storia_crawler,
    "imobiliare": run_imobiliare_crawler,
}


def get_crawler(source: str):
    return CRAWLER_REGISTRY.get(source)
