"""Hierarchical task display widget."""

from textual.widgets import Tree
from textual.widgets.tree import TreeNode
from typing import Optional

from sindri.core.tasks import TaskStatus


STATUS_ICONS = {
    TaskStatus.PENDING: "·",
    TaskStatus.PLANNING: "○",
    TaskStatus.WAITING: "◔",
    TaskStatus.RUNNING: "▶",
    TaskStatus.COMPLETE: "✓",
    TaskStatus.FAILED: "✗",
    TaskStatus.BLOCKED: "⚠",
}


class TaskTree(Tree):
    """Display task hierarchy with status icons."""

    def __init__(self, **kwargs):
        super().__init__("Tasks", **kwargs)
        self._task_nodes: dict[str, TreeNode] = {}
        self.root.expand()

    def add_task(
        self,
        description: str,
        task_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        status: TaskStatus = TaskStatus.PENDING
    ) -> str:
        """Add a task to the tree.

        Returns: task_id
        """
        import uuid
        task_id = task_id or str(uuid.uuid4())[:8]

        # Truncate long descriptions
        desc = description[:50] + "..." if len(description) > 50 else description
        label = f"[{STATUS_ICONS[status]}] {desc}"

        if parent_id and parent_id in self._task_nodes:
            parent_node = self._task_nodes[parent_id]
            node = parent_node.add(label, data={"id": task_id, "status": status})
            parent_node.expand()
        else:
            node = self.root.add(label, data={"id": task_id, "status": status})

        self._task_nodes[task_id] = node
        node.expand()
        return task_id

    def update_status(self, task_id: str, status: TaskStatus):
        """Update a task's status icon."""

        if task_id not in self._task_nodes:
            return

        node = self._task_nodes[task_id]
        old_label = str(node.label)

        # Replace status icon
        for old_status, icon in STATUS_ICONS.items():
            if f"[{icon}]" in old_label:
                new_label = old_label.replace(f"[{icon}]", f"[{STATUS_ICONS[status]}]")
                node.set_label(new_label)
                if node.data:
                    node.data["status"] = status
                break

    def clear_tree(self):
        """Clear all tasks from the tree."""
        self.root.remove_children()
        self._task_nodes.clear()
