"""Framework-free domain rules for VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE.

Everything in this package is deterministic and depends only on the Python
standard library (plus openpyxl for spreadsheet parsing). The FastAPI
routers and SQLAlchemy repositories call into these functions; the rules
themselves never touch the database or the network directly (retrieval
takes an injectable transport and resolver).
"""
