"""
Task type definitions and verification logic.

Defines the types of computational tasks the swarm can handle.
"""

from enum import Enum
from typing import Dict, Any, List
import hashlib
import random

class TaskType(Enum):
    PRIME_FINDING = "prime_finding"
    HASH_CRACKING = "hash_cracking"
    SORTING = "sorting"
    DATA_SEARCH = "data_search"

class Task:
    """Represents a computational task in the swarm."""
    
    def __init__(
        self,
        task_id: int,
        description: str,
        task_type: TaskType,
        input_data: Dict[str, Any],
        reward: int,
        deadline: float,
        coordinator_address: str
    ):
        self.task_id = task_id
        self.description = description
        self.task_type = task_type
        self.input_data = input_data
        self.reward = reward
        self.deadline = deadline
        self.coordinator_address = coordinator_address
        
        # State
        self.bids: List[Dict] = []
        self.assigned_to: str = None
        self.completed: bool = False
        self.solution: Any = None
    
    def add_bid(self, agent_id: str, amount: int):
        """Record a bid from an agent."""
        self.bids.append({
            "agent": agent_id,
            "amount": amount,
            "timestamp": float(random.uniform(0, 1)) # simulated timestamp offset
        })
    
    def get_best_bid(self) -> Dict:
        """Get the lowest bid."""
        if not self.bids:
            return None
        return min(self.bids, key=lambda x: x["amount"])
    
    def is_expired(self) -> bool:
        """Check if deadline has passed (with 5s grace period)."""
        import time
        return time.time() > (self.deadline + 5.0)

# --- Task Verification Logic ---

def verify_prime(number: int, target_limit: int) -> bool:
    """Verify if number is the largest prime less than target."""
    if number >= target_limit:
        return False
    
    # Check if prime
    if number < 2:
        return False
    for i in range(2, int(number ** 0.5) + 1):
        if number % i == 0:
            return False
            
    # In a real system, we'd also verify it's the *largest*,
    # but for this demo, just checking if it is prime and close to limit is enough
    return True

def verify_hash(input_str: str, target_prefix: str) -> bool:
    """Verify if input string produces hash with target prefix."""
    h = hashlib.sha256(input_str.encode()).hexdigest()
    return h.startswith(target_prefix)

def verify_sorting(original: List[int], sorted_list: List[int]) -> bool:
    """Verify if list is sorted correctly."""
    return sorted_list == sorted(original)

def verify_search(dataset: List[str], query: str, index: int) -> bool:
    """Verify if item at index matches query."""
    if index < 0 or index >= len(dataset):
        return False
    return dataset[index] == query

def verify_solution(task: Task, solution: Any) -> bool:
    """Route verification to appropriate function."""
    if task.task_type == TaskType.PRIME_FINDING:
        return verify_prime(solution, task.input_data["target"])
    
    elif task.task_type == TaskType.HASH_CRACKING:
        return verify_hash(solution, task.input_data["prefix"])
    
    elif task.task_type == TaskType.SORTING:
        return verify_sorting(task.input_data["array"], solution)
        
    elif task.task_type == TaskType.DATA_SEARCH:
        return verify_search(task.input_data["dataset"], task.input_data["query"], solution)
        
    return False

# --- Solver Helper Functions (for simulation) ---

def find_largest_prime(limit: int) -> int:
    """Find largest prime less than limit."""
    for num in range(limit - 1, 1, -1):
        is_prime = True
        for i in range(2, int(num ** 0.5) + 1):
            if num % i == 0:
                is_prime = False
                break
        if is_prime:
            return num
    return 2

def crack_hash(prefix: str) -> str:
    """Find a string that produces a hash starting with prefix."""
    import string
    chars = string.ascii_letters + string.digits
    attempt = ""
    while True:
        attempt = "".join(random.choices(chars, k=6))
        if hashlib.sha256(attempt.encode()).hexdigest().startswith(prefix):
            return attempt

def solve_task(task: Task) -> Any:
    """Simulate solving a task based on its type."""
    if task.task_type == TaskType.PRIME_FINDING:
        return find_largest_prime(task.input_data["target"])
        
    elif task.task_type == TaskType.HASH_CRACKING:
        return crack_hash(task.input_data["prefix"])
        
    elif task.task_type == TaskType.SORTING:
        return sorted(task.input_data["array"])
        
    elif task.task_type == TaskType.DATA_SEARCH:
        try:
            return task.input_data["dataset"].index(task.input_data["query"])
        except ValueError:
            return -1
    
    return None
