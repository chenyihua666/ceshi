"""
NL2SQL V4：支持完整的增删改查操作
改进：支持 SELECT / INSERT / UPDATE / DELETE 所有 SQL 操作
"""
import os
import json
import pymysql
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ========== LLM 配置 ==========
client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
MODEL = "qwen3.7-plus"


def call_llm(prompt: str) -> str:
    """调用 LLM 并返回纯文本"""
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
    'database': os.getenv('DB_NAME', 'wolin_student_system'),
    'charset': 'utf8mb4'
}
#12312312345
SCHEMA = """
数据库中有五张表：

1. students 表（学生信息）:
    -student_id: INT, 主键, 学生 ID
    -class_id: INT, 班级 ID（关联班级表）
    -name: VARCHAR(50), 学生姓名
    -hometown: VARCHAR(100), 生源地/家乡
    -graduate_school: VARCHAR(100), 毕业学校
    -major: VARCHAR(50), 专业
    -enrollment_date: DATE, 入学日期
    -graduation_date: DATE, 毕业日期
    -education: VARCHAR(20), 学历（如本科、硕士等）
    -consultant_id: INT, 顾问 ID（关联顾问表）
    -age: INT, 年龄
    -gender: CHAR(1), 性别（M/F）
    -is_delete: TINYINT(1), 逻辑删除标记（0-未删除，1-已删除）

2. class_info 表（班级信息）:
    -class_id: INT, 主键, 班级 ID
    -start_date: DATE, 开班日期/入学日期
    -head_teacher: VARCHAR(50), 班主任姓名   
    -course_teacher: VARCHAR(50), 任课教师/课程教师
3. employment 表（就业/录用信息）:
    -id: INT, 主键, 记录 ID
    -student_id: INT, 外键，关联学生 ID
    -student_name: VARCHAR(50), 学生姓名（冗余字段，便于查询）
    -class_id: INT, 外键，关联班级 ID
    -employment_open_date: DATE, 就业开放日期（或开始求职日期）
    -offer_date: DATE, 获得录用通知（Offer）的日期
    -company: VARCHAR(100), 录用公司名称
    -salary: DECIMAL(10,2), 薪资（单位可依业务约定，如元/月）
4.scores 表（学生考试成绩记录）:
    -id: INT, 主键, 记录 ID
    -student_id: INT, 外键，关联学生 ID
    -exam_order: INT, 考试次序/批次（如第1次月考、第2次模拟考等）
    -subject: VARCHAR(50), 考试科目（如数学、英语等）
    -score: DECIMAL(10,2), 考试成绩/分数
5.teachers 表（教师信息）:
    -teacher_id: INT, 主键, 教师 ID
    -name: VARCHAR(50), 教师姓名
    -managed_classes: VARCHAR(255), 管理的班级（可存储班级ID列表或班级名称，通常为冗余/汇总字段）
    -contact: VARCHAR(100), 联系方式（电话/邮箱等）
    -title: VARCHAR(50), 职称/头衔（如教授、高级讲师等）
    -remark: TEXT, 备注/附加说明

关系：一个学生有多条成绩记录（一对多）
查询时需要用 student_id 关联两张表。
"""

EXAMPLES = """
示例 1：
问题：张三的数学成绩是多少？
SQL：SELECT s.score FROM students st JOIN scores s ON st.student_id = s.student_id WHERE st.name = '张三' AND s.subject = '数学'

示例 2：
问题：一班所有学生的数学成绩
SQL：SELECT st.name, s.score FROM students st JOIN scores s ON st.student_id = s.student_id JOIN class_info c ON st.class_id = c.class_id WHERE c.class_id = 1 AND s.subject = '数学'

示例 3：
问题：数学成绩最高的学生是谁？
SQL：SELECT st.name, s.score FROM students st JOIN scores s ON st.student_id = s.student_id WHERE s.subject = '数学' ORDER BY s.score DESC LIMIT 1

示例 4：
问题：每个学生的平均成绩
SQL：SELECT st.name, AVG(s.score) as avg_score FROM students st JOIN scores s ON st.student_id = s.student_id GROUP BY st.student_id, st.name
"""


def generate_sql(question: str) -> list[str]:
    prompt = f"""
你是一个 MYSQL 专家。根据用户的问题、数据库表结构和示例，生成对应的 SQL 语句。

数据库表结构：
{SCHEMA}

示例：
{EXAMPLES}

用户问题：{question}

要求：
1. 只返回 JSON 格式的 SQL 字符串数组，不要其他解释
2. 根据意图生成合适的 SQL（SELECT 查询、INSERT 插入、UPDATE 更新、DELETE 删除）
3. 如果涉及多步操作，在数组中放多条 SQL
4. 使用正确的字段名和表名
5. 如果需要关联表，使用 JOIN

示例（返回 JSON 数组）：
["SELECT s.score FROM students st JOIN scores s ON st.student_id = s.student_id WHERE st.name = '张三' AND s.subject = '数学'"]

["INSERT INTO students (name, class_id, age, gender) VALUES ('思锦', 1, 20, 'F')", "INSERT INTO scores (student_id, subject, score, exam_order) VALUES (LAST_INSERT_ID(), '数学', 100.00, 1)"]
"""

    raw = call_llm(prompt).strip()
    raw = raw.replace('```json', '').replace('```', '').strip()

    sql_list = json.loads(raw)
    if isinstance(sql_list, str):
        return [sql_list]
    return sql_list


def execute_sql(sql_list: list[str]):
    """
    遍历执行 SQL 数组
    - SELECT: 返回最后一条查询的结果和列名
    - INSERT/UPDATE/DELETE: 返回受影响的行数并自动提交
    """
    conn = pymysql.connect(**DB_CONFIG)
    try:
        last_results, last_columns = None, []

        has_non_select = False
        for s in sql_list:
            with conn.cursor() as cursor:
                cursor.execute(s)
                sql_type = s.strip().upper().split()[0]

                if sql_type == 'SELECT':
                    last_results = cursor.fetchall()
                    last_columns = [desc[0] for desc in cursor.description] if cursor.description else []
                else:
                    has_non_select = True
                    affected = cursor.rowcount
                    last_results = affected
                    last_columns = None

        # 批量提交所有非查询 SQL
        if has_non_select:
            conn.commit()

        return last_results, last_columns
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ========== 新增：结果润色 ==========
def polish_result(question: str, sql: str, results: tuple, columns: list) -> str:

    prompt = f"""
你是一个友好的助手。根据用户的问题、执行的 SQL 和查询结果，尝试对结果进一步分析或总结。

用户问题：{question}
执行的 SQL：{sql}
列名：{columns}
查询结果：{results}

要求：
1. 500字以内简洁、自然的中文回答
2. 不要解释 SQL 或技术细节
3. 直接告诉用户答案

"""
    return call_llm(prompt).strip()


def nl2sql(question: str):
    if not question or not question.strip():
        print("❌ 问题不能为空")
        return None
    print(f"📝 用户问题：{question.strip()}")

    sql_list = generate_sql(question.strip())
    print(f"🔧 生成的 SQL：{sql_list}")

    try:
        result, columns = execute_sql(sql_list)

        # 以最后一条 SQL 的类型决定如何展示结果
        last_sql = sql_list[-1]
        sql_type = last_sql.strip().upper().split()[0]

        if sql_type == 'SELECT':
            print(f"✅ 查询结果：{result}")
            answer = polish_result(question, last_sql, result, columns)
            print(f"💬 AI 回答：{answer}")
        else:
            affected_rows = result
            op_names = {'INSERT': '插入', 'UPDATE': '更新', 'DELETE': '删除'}
            op_name = op_names.get(sql_type, '执行')
            print(f"✅ 成功{op_name}，影响 {affected_rows} 行数据")
            answer = f"已成功{op_name} {affected_rows} 行数据。"
            print(f"💬 AI 回答：{answer}")

        return result
    except ValueError as e:
        print(f"❌ SQL 校验失败：{e}")
        return None
    except Exception as e:
        print(f"❌ 执行失败：{e}")
        return None


if __name__ == '__main__':
    # 正常查询
    # nl2sql("浩天和思锦谁的数学成绩更好，差多少分他们？")
    #
    # print("\n" + "=" * 50 + "\n")
    #
    # 复杂查询（润色效果更明显）
    nl2sql("数学成绩最高和最低的学生是谁？")
    #
    # print("\n" + "=" * 50 + "\n")

    # # 测试危险操作（会被拦截）
    # nl2sql("帮我查询一下考试作弊导致成绩归0 的同学的相关考试信息和个人信息")