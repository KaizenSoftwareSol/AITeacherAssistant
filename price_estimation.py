# This script estimates the cost of using GPT-4o-mini for a given number of words.
def estimate_gpt4o_mini_cost(words, output_ratio=0.1, input_rate=0.15, output_rate=0.60): 
    tokens = words * 1.3
    input_tokens = tokens
    output_tokens = tokens * output_ratio
    cost_input = (input_tokens / 1000000) * input_rate
    cost_output = (output_tokens / 1000000) * output_rate
    total_cost = cost_input + cost_output
    return round(total_cost, 4)

if __name__ == "__main__":
    words = 259326
    print(f"Estimated cost: ${estimate_gpt4o_mini_cost(words)}")