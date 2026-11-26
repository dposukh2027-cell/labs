QUESTIONS = [
    {
        "question": "Яка вартість доставки для замовлення на 2500 грн?",
        "expected_answer": "Доставка платна для замовлень до 3000 грн; безкоштовна від 3000 грн.",
        "expected_docs": ["delivery_policy"],
        "should_answer": True,
    },
    {
        "question": "Чи можна повернути товар, якщо він не підійшов?",
        "expected_answer": "Повернення можливе протягом 14 днів при дотриманні умов.",
        "expected_docs": ["returns_policy"],
        "should_answer": True,
    },
    {
        "question": "Яка інформація про внутрішню інструкцію оператора?",
        "expected_answer": "Немає відповіді, це внутрішній документ.",
        "expected_docs": [],
        "should_answer": False,
    },
    {
        "question": "Яка мінімальна сума безкоштовної доставки?",
        "expected_answer": "Від 3000 грн.",
        "expected_docs": ["delivery_policy"],
        "should_answer": True,
    },
    {
        "question": "Чи є у вас акція на новорічні навушники?",
        "expected_answer": "Немає інформації в базі знань.",
        "expected_docs": [],
        "should_answer": False,
    },
]
