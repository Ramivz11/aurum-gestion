import mysql.connector
import streamlit as st

def get_db_connection():
    if "mysql" in st.secrets:
        return mysql.connector.connect(
            host=st.secrets["mysql"]["host"],
            user=st.secrets["mysql"]["user"],
            password=st.secrets["mysql"]["password"],
            database=st.secrets["mysql"]["database"],
            port=st.secrets["mysql"]["port"]
        )
    else:
        return mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="aurum_db"
        )

def migrate():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if 'envio' column exists in 'compras' table
        cursor.execute("SHOW COLUMNS FROM compras LIKE 'envio'")
        result = cursor.fetchone()
        
        if not result:
            print("Adding 'envio' column to 'compras' table...")
            cursor.execute("ALTER TABLE compras ADD COLUMN envio DECIMAL(10,2) DEFAULT 0.00")
            print("Column 'envio' added successfully.")
        else:
            print("Column 'envio' already exists in 'compras' table.")
            
        conn.commit()
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
