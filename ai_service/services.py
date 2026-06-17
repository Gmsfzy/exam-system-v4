from ai_service.client import AIClient
from database.models import Question, Major, QuestionTypeEnum, DifficultyEnum
from config import Config
from database import db
import json
import re

ai_client = AIClient()

def clean_json_text(text: str) -> str:
    """清洗AI返回文本，提取纯JSON字符串"""
    # 移除markdown代码块标记、换行、空格干扰
    text = re.sub(r'```(json)?', '', text)
    text = text.strip()
    return text

def ai_generate_questions(db, major_id: int, question_type: str, difficulty: str, count: int = 5):
    """使用AI生成题目并保存到数据库"""
    major = db.get(Major, major_id)
    if not major:
        raise ValueError("专业不存在")

    # 调用AI
    result = ai_client.generate_question(major.name, question_type, difficulty, count)
    # 清洗文本
    clean_text = clean_json_text(result)
    questions = []

    try:
        data_list = json.loads(clean_text)
        if isinstance(data_list, list):
            for data in data_list:
                if data.get("content") and data.get("answer"):
                    question = Question(
                        content=data["content"],
                        options=json.dumps(data.get("options", [])) if data.get("options") else None,
                        answer=data["answer"],
                        analysis=data.get("analysis", ""),
                        major_id=major_id,
                        type=question_type,
                        difficulty=difficulty
                    )
                    db.add(question)
                    questions.append(question)
    except json.JSONDecodeError as e:
        raise Exception(f"AI返回内容不是有效JSON: {str(e)}，原始内容：{clean_text}")

    db.commit()
    return questions

def ai_grade_exam(db, exam_id: int, student_id: int):
    """AI批改考试：客观题本地比对，主观题调AI并标记人工评分"""
    from database.models import ExamSession, Answer, ExamQuestion, Question

    session = ExamSession.query.filter_by(exam_id=exam_id, student_id=student_id).first()
    if not session:
        raise ValueError("考试会话不存在")

    answers = Answer.query.filter_by(session_id=session.id).all()

    total_score = 0
    earned_score = 0
    OBJECTIVE_TYPES = {'single_choice', 'multiple_choice', 'true_false', 'fill_blank'}

    for answer in answers:
        exam_question = ExamQuestion.query.filter_by(exam_id=exam_id, question_id=answer.question_id).first()
        question = db.get(Question, answer.question_id)

        if not (exam_question and question):
            continue

        total_score += exam_question.score
        student_ans = (answer.student_answer or '').strip()
        correct_ans = (question.answer or '').strip()

        # 主观题标记需要人工评分，并调用AI语义批改
        if QuestionTypeEnum.is_subjective(question.type):
            answer.needs_manual_grade = True
            try:
                result = ai_client.grade_answer(question.content, question.answer, student_ans)
                data = json.loads(result)
                answer.is_correct = data.get('is_correct', False)
                answer.score = (data.get('score', 0) / 100) * exam_question.score
                earned_score += answer.score
            except Exception:
                # AI 调用失败，主观题先给 0 分，等人工评分
                answer.is_correct = False
                answer.score = 0
            continue

        # ── 客观题：本地比对 ──────────────────────────────
        if question.type == 'multiple_choice':
            # 多选题：按字符排序后比较（允许答案顺序不同）
            s_sorted = ''.join(sorted(student_ans.upper()))
            c_sorted = ''.join(sorted(correct_ans.upper()))
            is_correct = s_sorted == c_sorted
        elif question.type == 'fill_blank':
            # 填空题：忽略大小写和多余空格
            is_correct = student_ans.lower() == correct_ans.lower()
        else:
            # 单选题 / 判断题：完全匹配（忽略大小写）
            is_correct = student_ans.upper() == correct_ans.upper()

        answer.is_correct = is_correct
        answer.score = exam_question.score if is_correct else 0
        earned_score += answer.score

    db.commit()
    return earned_score, total_score

def ai_generate_analysis(db, question_id: int, student_answer: str):
    """生成单题解析"""
    from database import db as _db
    question = _db.session.get(Question, question_id)
    if not question:
        raise ValueError("题目不存在")

    result = ai_client.generate_analysis(question.content, question.answer, student_answer)

    return result
