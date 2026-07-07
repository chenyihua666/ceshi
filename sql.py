"""
NL2SQL：自然语言转 SQL 并执行，支持 SELECT/INSERT/UPDATE/DELETE + 结果润色
"""
import os
import sys
import json
import pymysql
from openai import OpenAI
from dotenv import load_dotenv

# 强制 stdout 为 UTF-8，解决 Windows CMD 中文/emoji 乱码
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# 加载 .env（优先从当前目录，其次从 nl2sql/ 目录）
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nl2sql', '.env'))

# ========== LLM 配置 ==========
client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
MODEL = "qwen3.7-plus"


def call_llm(prompt: str) -> str:
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content


# ========== 数据库配置 ==========
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', '123456'),
    'database': os.getenv('DB_NAME', 'test'),
    'charset': 'utf8mb4'
}

# ========== 表结构描述 ==========
SCHEMA = """
数据库中有以下表：

1. students 表（学生信息）:
    -student_id: INT, 主键, 自增
    -class_id: INT, 外键，关联 class_info.class_id
    -name: VARCHAR(50), 学生姓名
    -hometown: VARCHAR(100), 家乡
    -graduate_school: VARCHAR(200), 毕业学校
    -major: VARCHAR(200), 专业
    -enrollment_date: DATE, 入学日期
    -graduation_date: DATE, 毕业日期
    -education: VARCHAR(50), 学历
    -consultant_id: INT, 顾问ID
    -age: INT, 年龄
    -gender: VARCHAR(10), 性别
    -is_delete: TINYINT(1), 是否删除(0=否,1=是)

2. scores 表（考试成绩）:
    -id: INT, 主键, 自增
    -student_id: INT, 外键，关联 students.student_id
    -exam_order: INT, 考试次数(1/2/3...)
    -score: FLOAT, 分数

3. teachers 表（老师信息）:
    -teacher_id: INT, 主键, 自增
    -name: VARCHAR(50), 老师姓名
    -managed_classes: VARCHAR(500), 管理的班级
    -contact: VARCHAR(100), 联系方式
    -title: VARCHAR(100), 职称
    -remark: VARCHAR(500), 备注

4. class_info 表（班级信息）:
    -class_id: INT, 主键, 自增
    -start_date: DATE, 开班日期
    -head_teacher: VARCHAR(50), 班主任
    -course_teacher: VARCHAR(50), 授课老师

5. employment 表（就业信息）:
    -id: INT, 主键, 自增
    -student_id: INT, 外键，关联 students.student_id
    -student_name: VARCHAR(50), 学生姓名
    -class_id: INT, 外键，关联 class_info.class_id
    -employment_open_date: DATE, 就业开放日期
    -offer_date: DATE, offer日期
    -company: VARCHAR(200), 公司名称
    -salary: FLOAT, 薪资

关系：
- students.class_id -> class_info.class_id（学生属于某个班级）
- scores.student_id -> students.student_id（一个学生有多条考试成绩）
- employment.student_id -> students.student_id（一个学生有一条就业记录）
"""

# ========== Few-shot 训练样本 ==========
EXAMPLES = """
示例 1：
问题：查询所有学生
SQL：SELECT * FROM students WHERE is_delete = 0

示例 2：
问题：张三的考试成绩是多少？
SQL：SELECT s.name, sc.exam_order, sc.score FROM students s JOIN scores sc ON s.student_id = sc.student_id WHERE s.name = '张三'

示例 3：
问题：每个班级有多少学生？
SQL：SELECT c.class_id, COUNT(*) as student_count FROM class_info c JOIN students s ON c.class_id = s.class_id WHERE s.is_delete = 0 GROUP BY c.class_id

示例 4：
问题：添加一个叫李四的学生，25岁，来自北京
SQL：INSERT INTO students (name, age, hometown) VALUES ('李四', 25, '北京')

示例 5：
问题：把张三的年龄改成30
SQL：UPDATE students SET age = 30 WHERE name = '张三'

示例 6：
问题：删除分数为空的成绩记录
SQL：DELETE FROM scores WHERE score IS NULL

示例 7：
问题：平均分最高的学生是谁？
SQL：SELECT s.name, AVG(sc.score) as avg_score FROM students s JOIN scores sc ON s.student_id = sc.student_id GROUP BY s.student_id, s.name ORDER BY avg_score DESC LIMIT 1

示例 8：
问题：每个学生的家乡是哪里？
SQL：SELECT name, hometown FROM students WHERE is_delete = 0
"""


# ========== SQL 生成 ==========
def generate_sql(question: str) -> list:
    prompt = f"""
你是一个 MySQL 专家。根据用户的问题、数据库表结构和示例，生成对应的 SQL 语句。

数据库表结构：
{SCHEMA}

训练样本：
{EXAMPLES}

用户问题：{question}

要求：
1. 只返回 JSON 格式的 SQL 字符串数组，不要任何其他文字
2. 根据用户意图生成合适的 SQL（SELECT / INSERT / UPDATE / DELETE）
3. 多步操作时在数组中放多条 SQL
4. 务必使用正确的字段名和表名
5. 联表查询时使用 JOIN

返回格式示例：
["SELECT * FROM users"]
["INSERT INTO users (name, age) VALUES ('王五', 22)"]
["UPDATE users SET city = '上海' WHERE name = '张三'", "SELECT * FROM users WHERE name = '张三'"]
"""
    raw = call_llm(prompt).strip()
    raw = raw.replace('```json', '').replace('```', '').strip()
    sql_list = json.loads(raw)
    if isinstance(sql_list, str):
        return [sql_list]
    return sql_list


# ========== SQL 执行 ==========
def execute_sql(sql_list: list):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        last_results, last_columns = None, []
        has_write = False
        for s in sql_list:
            with conn.cursor() as cursor:
                cursor.execute(s)
                sql_type = s.strip().upper().split()[0]
                if sql_type == 'SELECT':
                    last_results = cursor.fetchall()
                    last_columns = [desc[0] for desc in cursor.description] if cursor.description else []
                else:
                    has_write = True
                    last_results = cursor.rowcount
                    last_columns = None
        if has_write:
            conn.commit()
        return last_results, last_columns, has_write
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ========== 结果润色 ==========
def polish_result(question: str, sql: str, results, columns: list) -> str:
    prompt = f"""
你是一个友好的数据助手。根据用户问题、执行的 SQL 和查询结果，用自然语言简洁回答。

用户问题：{question}
执行的 SQL：{sql}
列名：{columns}
查询结果：{results}

要求：
1. 200字以内，简洁自然
2. 不要解释 SQL 或技术细节
3. 直接告诉用户答案
"""
    return call_llm(prompt).strip()


# ========== 主流程 ==========
def nl2sql(question: str):
    if not question or not question.strip():
        print("[ERROR] 问题不能为空")
        return None

    question = question.strip()
    print(f"[Q] 问题：{question}")

    # 1. 生成 SQL
    sql_list = generate_sql(question)
    print(f"[SQL] {sql_list}")

    # 2. 执行 SQL
    try:
        result, columns, has_write = execute_sql(sql_list)
    except Exception as e:
        print(f"[ERROR] 执行失败：{e}")
        return None

    # 3. 展示结果
    last_sql = sql_list[-1]
    sql_type = last_sql.strip().upper().split()[0]

    if sql_type == 'SELECT':
        print(f"[OK] 查询结果：{result}")
        answer = polish_result(question, last_sql, result, columns)
        print(f"[A] 回答：{answer}")
    else:
        op_names = {'INSERT': '插入', 'UPDATE': '更新', 'DELETE': '删除'}
        op_name = op_names.get(sql_type, '执行')
        print(f"[OK] {op_name}成功，影响 {result} 行")
        print(f"[A] 回答：已成功{op_name} {result} 行数据。")

    return result


# ========== 测试 ==========
if __name__ == '__main__':
    # 查询所有学生
    nl2sql("查询所有学生")
    print("\n" + "=" * 50 + "\n")

    # 联表查询
    nl2sql("每个班级有多少学生？")
    print("\n" + "=" * 50 + "\n")

    # 聚合查询
    nl2sql("每个学生的平均分是多少？")
