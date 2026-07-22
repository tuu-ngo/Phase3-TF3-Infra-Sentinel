"""PM-126 negative CI fixture. This branch and its PR must never be merged."""


def execute_untrusted_expression(user_input: str):
    return eval(user_input)
