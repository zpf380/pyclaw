#!/usr/bin/env python3
"""直接使用sqlite3模块查询数据库"""

import sqlite3
import os

def query_database():
    """直接查询SQLite数据库"""
    db_path = "pyclaw.db"
    
    if not os.path.exists(db_path):
        print(f"数据库文件 {db_path} 不存在")
        return
    
    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("=== 直接SQL查询 ===")
        
        # 查看所有表
        print("\n1. 所有表:")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        for table in tables:
            print(f"   - {table[0]}")
        
        # 查看技能表结构
        print("\n2. 技能表结构:")
        cursor.execute("PRAGMA table_info(skills);")
        columns = cursor.fetchall()
        for col in columns:
            print(f"   - {col[1]}: {col[2]}")
        
        # 查看消息表结构
        print("\n3. 消息表结构:")
        cursor.execute("PRAGMA table_info(messages);")
        columns = cursor.fetchall()
        for col in columns:
            print(f"   - {col[1]}: {col[2]}")
        
        # 查看技能数据
        print("\n4. 技能数据:")
        cursor.execute("SELECT * FROM skills;")
        skills = cursor.fetchall()
        if skills:
            for skill in skills:
                print(f"   ID: {skill[0]}, 名称: {skill[1]}, 编码: {skill[2]}, 状态: {skill[4]}")
        else:
            print("   暂无数据")
        
        # 查看消息数据
        print("\n5. 消息数据 (最新5条):")
        cursor.execute("SELECT * FROM messages ORDER BY timestamp DESC LIMIT 5;")
        messages = cursor.fetchall()
        if messages:
            for msg in messages:
                print(f"   ID: {msg[0]}, 会话: {msg[1]}, 类型: {msg[3]}")
                print(f"   内容: {msg[2][:60]}..." if len(msg[2]) > 60 else f"   内容: {msg[2]}")
                print(f"   时间: {msg[6]}")
                print("   " + "-" * 40)
        else:
            print("   暂无数据")
        
        # 关闭连接
        conn.close()
        
    except Exception as e:
        print(f"查询失败: {e}")

if __name__ == "__main__":
    query_database()