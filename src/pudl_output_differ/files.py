"""Generic utilities for diffing PUDL_OUTPUT directories."""

from pathlib import Path
from queue import Queue
from typing import Iterator

import fsspec
from pudl_output_differ.sqlite import SQLiteDBEvaluator

from pudl_output_differ.types import (
    DiffEvaluator, DiffEvaluatorBase, DiffTreeNode, KeySetDiff
)


class OutputDirectoryEvaluator(DiffEvaluatorBase):
    """Represents diff between two directories."""
    left_path: str
    right_path: str

    def get_files(self, root_path: str) -> dict[str, str]:
        """Returns list of files in the output directory.

        The files are returned in a dictionary where keys are
        relative paths to the files and values are fully qualified
        paths.
        """
        # TODO(rousik): check if root_path is an actual directory.
        out: dict[str, str] = {}
        # FIXME(rousik): glob doesn't actually do recursive search here,
        # at least not for local files.
        fs = fsspec.filesystem("file")
        # TODO(rousik): add support for gcs here, with potential init params
        # needed (pydantic BaseSettings might help here).
        for fpath in fs.glob(root_path + "/*"):
            # FIXME(rousik): following might not work with remote paths.
            rel_path = Path(fpath).relative_to(root_path).as_posix()
            out[rel_path] = fpath
        return out

    # TODO(rousik): passing parents this way is a bit clunky, but acceptable.
    def execute(self, task_queue: Queue[DiffEvaluator]) -> Iterator[DiffTreeNode]:
        """Computes diff between two output directories.

        Files on the left and right are compared for presence, children
        are deeper-layer analyzers for specific file types that are supported.
        """
        lfs = self.get_files(self.left_path)
        rfs = self.get_files(self.right_path)

        files_node = self.parent_node.add_child(
            DiffTreeNode(
                name="Files",
                diff=KeySetDiff.from_sets(set(lfs), set(rfs)),
            )
        )
        for shared_file in files_node.diff.shared:
            if shared_file.endswith(".sqlite"):
                # TODO(rousik): use fsspect to pull remote databases
                # to local cache.
                task_queue.put(
                    SQLiteDBEvaluator(
                        db_name=shared_file,
                        left_db_path=lfs[shared_file],
                        right_db_path=rfs[shared_file],
                        parent_node = files_node,
                    )
                )
        yield files_node