"""
SQL-Guardian Database Toolkits

Provides specialized database toolkits for HR and Sales databases with the Gemini LLM.
"""

import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit


load_dotenv()

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-lite",
    temperature=0,
    max_tokens=2048,
    max_retries=2,
    streaming=False,
    model_kwargs={"top_p": 0.95, "top_k": 40}
)

HR_DATABASE_URI = "sqlite:///./data/hr.db"
SALES_DATABASE_URI = "sqlite:///./data/sales.db"

hr_db = SQLDatabase.from_uri(HR_DATABASE_URI)
sales_db = SQLDatabase.from_uri(SALES_DATABASE_URI)

hr_toolkit = SQLDatabaseToolkit(db=hr_db, llm=llm)
sales_toolkit = SQLDatabaseToolkit(db=sales_db, llm=llm)


def _prepare_tools(tools, prefix: str, domain_description: str):
    """Prefix tool names and enrich descriptions for disambiguation."""
    prepared = []
    for tool in tools:
        original_name = tool.name
        tool.name = f"{prefix}_{original_name}"
        original_description = tool.description
        tool.description = (
            f"For queries against the {domain_description}. "
            f"Use this when working with the {prefix.upper()} dataset. "
            f"(Original tool: {original_name}) "
            f"{original_description}"
        )
        prepared.append(tool)
    return prepared


hr_tools = _prepare_tools(hr_toolkit.get_tools(), "hr", "Human Resources (HR) Database")
sales_tools = _prepare_tools(sales_toolkit.get_tools(), "sales", "Sales Database")

all_tools = hr_tools + sales_tools

__all__ = [
    'llm',
    'hr_db',
    'sales_db', 
    'hr_toolkit',
    'sales_toolkit',
    'hr_tools',
    'sales_tools',
    'all_tools'
]