#!/usr/bin/env python3
"""
SQL-Guardian Database Setup Script

Creates and seeds two SQLite databases: HR and Sales.
"""

import os
import sqlite3
from datetime import datetime, timedelta


def ensure_data_directory():
    """Create the data directory if it doesn't exist."""
    data_dir = "data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)


def create_hr_database():
    """Create and seed the HR database."""
    db_path = "data/hr.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA foreign_keys = ON")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL UNIQUE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) NOT NULL UNIQUE,
            hire_date DATE NOT NULL,
            dept_id INTEGER NOT NULL,
            FOREIGN KEY (dept_id) REFERENCES departments (id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS salaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount DECIMAL(10, 2) NOT NULL,
            effective_date DATE NOT NULL,
            emp_id INTEGER NOT NULL,
            FOREIGN KEY (emp_id) REFERENCES employees (id)
        )
    """)
    
    cursor.execute("SELECT COUNT(*) FROM departments")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return
    
    departments = [
        ("Engineering",),
        ("Human Resources",),
        ("Marketing",),
        ("Sales",),
        ("Finance",),
        ("Operations",),
        ("Product Management",),
        ("Customer Support",)
    ]
    
    cursor.executemany("INSERT OR IGNORE INTO departments (name) VALUES (?)", departments)
    
    employees = [
        ("Alice Johnson", "alice.johnson@company.com", "2022-01-15", 1),
        ("Bob Smith", "bob.smith@company.com", "2021-03-22", 1),
        ("Carol Davis", "carol.davis@company.com", "2023-02-10", 2),
        ("David Wilson", "david.wilson@company.com", "2020-11-05", 3),
        ("Eve Brown", "eve.brown@company.com", "2022-07-18", 4),
        ("Frank Miller", "frank.miller@company.com", "2021-09-30", 5),
        ("Grace Lee", "grace.lee@company.com", "2023-01-08", 1),
        ("Henry Taylor", "henry.taylor@company.com", "2022-05-14", 6),
        ("Ivy Chen", "ivy.chen@company.com", "2021-12-03", 7),
        ("Jack Williams", "jack.williams@company.com", "2023-04-25", 8)
    ]
    
    cursor.executemany("""
        INSERT OR IGNORE INTO employees (name, email, hire_date, dept_id) 
        VALUES (?, ?, ?, ?)
    """, employees)
    
    salaries = [
        (75000.00, "2022-01-15", 1),
        (85000.00, "2023-01-15", 1),
        (80000.00, "2021-03-22", 2),
        (87000.00, "2022-03-22", 2),
        (65000.00, "2023-02-10", 3),
        (72000.00, "2020-11-05", 4),
        (78000.00, "2021-11-05", 4),
        (68000.00, "2022-07-18", 5),
        (95000.00, "2021-09-30", 6),
        (82000.00, "2023-01-08", 7),
        (71000.00, "2022-05-14", 8),
        (88000.00, "2021-12-03", 9),
        (58000.00, "2023-04-25", 10),
    ]
    
    cursor.executemany("""
        INSERT OR IGNORE INTO salaries (amount, effective_date, emp_id) 
        VALUES (?, ?, ?)
    """, salaries)
    
    conn.commit()
    conn.close()


def create_sales_database():
    """Create and seed the Sales database."""
    db_path = "data/sales.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA foreign_keys = ON")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) NOT NULL UNIQUE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            price DECIMAL(10, 2) NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME NOT NULL,
            customer_id INTEGER NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers (id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quantity INTEGER NOT NULL,
            unit_price DECIMAL(10, 2) NOT NULL,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    """)
    
    cursor.execute("SELECT COUNT(*) FROM customers")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return
    
    customers = [
        ("TechCorp Solutions", "orders@techcorp.com"),
        ("Global Enterprises", "purchasing@globalent.com"),
        ("StartupX", "admin@startupx.io"),
        ("MegaRetail Inc", "procurement@megaretail.com"),
        ("InnovateLab", "finance@innovatelab.org"),
        ("DataDriven LLC", "contracts@datadriven.com"),
        ("CloudFirst Co", "billing@cloudfirst.net"),
        ("AgileWorks", "accounts@agileworks.com"),
        ("FutureScale", "orders@futurescale.ai"),
        ("NextGen Systems", "purchase@nextgensys.com")
    ]
    
    cursor.executemany("INSERT OR IGNORE INTO customers (name, email) VALUES (?, ?)", customers)
    
    products = [
        ("Enterprise Software License", 2999.99),
        ("Cloud Storage Plan", 299.99),
        ("Premium Support Package", 1499.99),
        ("Data Analytics Platform", 4999.99),
        ("Security Monitoring Tool", 899.99),
        ("API Gateway Service", 1299.99),
        ("Machine Learning Platform", 3999.99),
        ("Database Management System", 2499.99),
        ("Development Tools Suite", 799.99),
        ("Collaboration Platform", 599.99)
    ]
    
    cursor.executemany("INSERT OR IGNORE INTO products (name, price) VALUES (?, ?)", products)
    
    base_date = datetime.now() - timedelta(days=90)
    orders = []
    for i in range(15):
        order_date = base_date + timedelta(days=i*6)
        customer_id = (i % 10) + 1
        orders.append((order_date.strftime("%Y-%m-%d %H:%M:%S"), customer_id))
    
    cursor.executemany("INSERT OR IGNORE INTO orders (created_at, customer_id) VALUES (?, ?)", orders)
    
    order_items = [
        (2, 2999.99, 1, 1),
        (1, 1499.99, 1, 3),
        (5, 299.99, 2, 2),
        (1, 4999.99, 3, 4),
        (3, 899.99, 3, 5),
        (1, 1299.99, 4, 6),
        (2, 3999.99, 5, 7),
        (1, 2499.99, 5, 8),
        (10, 799.99, 6, 9),
        (1, 599.99, 7, 10),
        (3, 2999.99, 8, 1),
        (2, 1499.99, 8, 3),
        (1, 4999.99, 9, 4),
        (5, 299.99, 10, 2),
        (1, 899.99, 10, 5),
        (1, 1299.99, 11, 6),
        (2, 799.99, 11, 9),
        (1, 3999.99, 12, 7),
        (4, 599.99, 13, 10),
        (1, 2499.99, 14, 8),
        (1, 1499.99, 14, 3),
        (2, 4999.99, 15, 4),
    ]
    
    cursor.executemany("""
        INSERT OR IGNORE INTO order_items (quantity, unit_price, order_id, product_id) 
        VALUES (?, ?, ?, ?)
    """, order_items)
    
    conn.commit()
    conn.close()


def verify_databases():
    """Verify both databases were created successfully."""
    try:
        conn = sqlite3.connect("data/hr.db")
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM departments")
        dept_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM employees")
        emp_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM salaries")
        sal_count = cursor.fetchone()[0]
        
        conn.close()
        
        print(f"HR Database: {dept_count} departments, {emp_count} employees, {sal_count} salary records")
        
    except Exception as e:
        print(f"Error verifying HR database: {e}")
    
    try:
        conn = sqlite3.connect("data/sales.db")
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM customers")
        cust_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM products")
        prod_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM orders")
        order_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM order_items")
        item_count = cursor.fetchone()[0]
        
        conn.close()
        
        print(f"Sales Database: {cust_count} customers, {prod_count} products, {order_count} orders, {item_count} order items")
        
    except Exception as e:
        print(f"Error verifying Sales database: {e}")


def main():
    """Create and seed both databases."""
    ensure_data_directory()
    create_hr_database()
    create_sales_database()
    verify_databases()


if __name__ == "__main__":
    main()