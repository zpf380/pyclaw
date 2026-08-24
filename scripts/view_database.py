#!/usr/bin/env python3
"""查看SQLite数据库内容"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pyclaw.database.database import DatabaseManager

def view_database():
    """查看数据库内容"""
    print("=== SQLite数据库内容查看 ===")
    
    try:
        # 初始化数据库管理器
        db_manager = DatabaseManager()
        
        # 查看技能表
        print("\n[技能表] (skills):")
        print("-" * 50)
        skills = db_manager.get_all_skills()
        if skills:
            for skill in skills:
                print(f"ID: {skill['id']}")
                print(f"  名称: {skill['name']}")
                print(f"  编码: {skill['code']}")
                print(f"  描述: {skill['description']}")
                print(f"  状态: {skill['status']}")
                print(f"  创建时间: {skill['createTime']}")
                print(f"  更新时间: {skill['updateTime']}")
                print("-" * 30)
        else:
            print("  暂无技能数据")
        
        # 查看消息表
        print("\n[消息表] (messages):")
        print("-" * 50)
        messages = db_manager.get_messages_by_session("default", 20)
        if messages:
            for msg in messages:
                print(f"ID: {msg['id']}")
                print(f"  会话ID: {msg['session_id']}")
                print(f"  内容: {msg['content'][:50]}..." if len(msg['content']) > 50 else f"  内容: {msg['content']}")
                print(f"  类型: {msg['type']}")  # 修正字段名
                print(f"  发送者: {msg['sender']}")
                print(f"  接收者: {msg['receiver']}")
                print(f"  时间: {msg['time']}")  # 修正字段名
                print("-" * 30)
        else:
            print("  暂无消息数据")
        
        # 查看统计信息
        print("\n[统计信息]:")
        print("-" * 50)
        print(f"技能数量: {len(skills)}")
        print(f"消息数量: {len(messages)}")
        
    except Exception as e:
        print(f"查看数据库失败: {e}")

if __name__ == "__main__":
    view_database()