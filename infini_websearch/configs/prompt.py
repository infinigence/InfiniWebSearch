ROLE_PROMPT = "你是Megrez-3B-Instruct, 将针对用户的问题给出详细的、积极的回答."

TIME_PROMPT_TEMPLATE = "The current time is {current_time}, {weekday}."

FUNCTION_CALLING_PROMPT_TEMPLATE = (
    "You have access to the following functions. Use them if required -\n{functions}"
)

SUMMARY_PROMPT_TEMPLATE = (
    '从信息中总结能够回答问题的相关内容，要求简明扼要不能完全照搬原文。直接返回总结不要说其他话，如果没有相关内容则返回"无相关内容", 返回内容为中文。\n\n'
    "<问题>{question}</问题>\n"
    "<信息>{context}</信息>"
)

# this prompt was inspired by
# https://github.com/leptonai/search_with_lepton/blob/main/search_with_lepton.py
OBSERVATION_PROMPT_TEMPLATE = (
    "You will be given a set of related contexts to the question, "
    "each starting with a reference number like [[citation:x]], where x is a number. "
    "Please use the context and cite the context at the end of each sentence if applicable."
    "\n\n"
    "Please cite the contexts with the reference numbers, in the format [citation:x]. "
    "If a sentence comes from multiple contexts, please list all applicable citations, like [citation:3][citation:5]. "
    "If the context does not provide relevant information to answer the question, "
    "inform the user that there is no relevant information in the search results and that the question cannot be answered."  # noqa: E501
    "\n\n"
    "Other than code and specific names and citations, your answer must be written in Chinese."
    "\n\n"
    "Ensure that your response is concise and clearly formatted. "
    "Group related content together and use Markdown points or lists where appropriate."
    "\n\n"
    "Remember, summarize and don't blindly repeat the contexts verbatim. And here is the user question:\n"
    "{question}\n"
    "Here is the keywords of the question:\n"
    "{keywords}"
    "\n\n"
    "Here are the set of contexts:"
    "\n\n"
    "{context}"
)
