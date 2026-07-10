import importlib
import os


def test_catalog_addr_uses_frontend_proxy_config():
    os.environ.pop("CATALOG_ADDR", None)
    os.environ["FRONTEND_PROXY_ADDR"] = "localhost:8080"
    import tools.catalog_tool as catalog_tool
    importlib.reload(catalog_tool)
    assert catalog_tool.CATALOG_ADDR == "localhost:8080"
