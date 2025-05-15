from pocketflow import Flow, Node

# Create a simple EndNode
class EndNode(Node):
    def prep(self, shared):
        return None
    
    def exec(self, _):
        return None
    
    def post(self, shared, prep_res, exec_res):
        return None

# Import nodes after defining EndNode to avoid circular imports
from nodes import GetUserQuestionNode, RetrieveNode, AnswerNode, EmbedNodeLong, EmbedNodeShort

def create_chat_flow():
    # Create the nodes
    question_node = GetUserQuestionNode()
    retrieve_node = RetrieveNode()
    answer_node = AnswerNode()
    embed_node_long = EmbedNodeLong()
    embed_node_short = EmbedNodeShort()
    end_node = EndNode()
    
    # Connect the flow:
    # 1. Start with getting a question
    # 2. Retrieve relevant conversations
    # 3. Generate an answer
    # 4. Optionally embed old conversations
    # 5. Loop back to get the next question

    # Main flow path
    question_node - "retrieve" >> retrieve_node
    retrieve_node - "answer" >> answer_node
    
    # When we need to embed old conversations
    answer_node - "embed" >> embed_node_short
    embed_node_short - "decide_long_term" >> embed_node_long
    embed_node_long - "question" >> question_node
    
    # Loop back for next question
    answer_node - "question" >> question_node
    # embed_node - "question" >> question_node
    # embed_node_short - "question" >> question_node
    
    # Add exit path
    question_node - "exit" >> end_node
    
    # Create the flow starting with question node
    return Flow(start=question_node)

# Initialize the flow
chat_flow = create_chat_flow()