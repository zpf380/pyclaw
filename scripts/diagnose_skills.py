#!/usr/bin/env python3
"""诊断技能操作问题"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pyclaw.database.database import DatabaseManager

def diagnose_skills():
    """诊断技能操作问题"""
    print("=== 技能操作诊断 ===")
    
    try:
        # 初始化数据库管理器
        db_manager = DatabaseManager()
        
        # 1. 检查当前技能数据
        print("\n1. 当前技能数据:")
        skills = db_manager.get_all_skills()
        print(f"技能数量: {len(skills)}")
        for skill in skills:
            print(f"  - ID: {skill['id']}, 名称: {skill['name']}, 编码: {skill['code']}")
        
        # 2. 测试添加技能
        print("\n2. 测试添加技能:")
        result = db_manager.add_skill("诊断技能", "diagnose_skill", "用于诊断的技能")
        print(f"添加结果: {result}")
        
        # 3. 检查添加后的技能数据
        print("\n3. 添加后的技能数据:")
        skills = db_manager.get_all_skills()
        print(f"技能数量: {len(skills)}")
        for skill in skills:
            print(f"  - ID: {skill['id']}, 名称: {skill['name']}, 编码: {skill['code']}")
        
        # 4. 测试更新技能
        if skills:
            print("\n4. 测试更新技能:")
            skill_id = skills[0]['id']
            result = db_manager.update_skill(skill_id, name="更新后的诊断技能", description="已更新的描述")
            print(f"更新结果: {result}")
        
        # 5. 检查更新后的技能数据
        print("\n5. 更新后的技能数据:")
        skills = db_manager.get_all_skills()
        print(f"技能数量: {len(skills)}")
        for skill in skills:
            print(f"  - ID: {skill['id']}, 名称: {skill['name']}, 编码: {skill['code']}")
        
        # 6. 测试删除技能
        if skills:
            print("\n6. 测试删除技能:")
            skill_id = skills[0]['id']
            result = db_manager.delete_skill(skill_id)
            print(f"删除结果: {result}")
        
        # 7. 检查删除后的技能数据
        print("\n7. 删除后的技能数据:")
        skills = db_manager.get_all_skills()
        print(f"技能数量: {len(skills)}")
        for skill in skills:
            print(f"  - ID: {skill['id']}, 名称: {skill['name']}, 编码: {skill['code']}")
        
        # 8. 检查数据库中的实际数据
        print("\n8. 数据库中的实际技能数据:")
        import sqlite3
        conn = sqlite3.connect('pyclaw.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skills;")
        db_skills = cursor.fetchall()
        print(f"数据库中的技能数量: {len(db_skills)}")
        for skill in db_skills:
            print(f"  - ID: {skill[0]}, 名称: {skill[1]}, 编码: {skill[2]}")
        conn.close()
        
    except Exception as e:
        print(f"诊断过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    diagnose_skills()