import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.run_workflow import (
    INPUT_FILES,
    PROCESSING_STEPS,
    WorkflowStepError,
    run_workflow,
)


class RunWorkflowTest(unittest.TestCase):
    def test_uploads_inputs_runs_pipeline_and_returns_html(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            uploads = {key: f"{key}-workbook".encode() for key in INPUT_FILES}

            def run_step(command, **_kwargs):
                self.assertEqual(_kwargs["cwd"], project_root)
                script = Path(command[-1]).relative_to(project_root).as_posix()
                if script == "src/consolidacao.py":
                    processed_dir = project_root / "data" / "processed"
                    processed_dir.mkdir(parents=True)
                    for filename in (
                        "tatica_arvore.csv",
                        "tatica_delta.csv",
                        "calendario_arvore.csv",
                        "ctr_arvore.csv",
                        "arvore_precos.csv",
                    ):
                        (processed_dir / filename).write_text("processed")
                elif script == "scripts/build_static_site.py":
                    html_path = (
                        project_root
                        / "site-premium"
                        / "arvore_precos_premium.html"
                    )
                    html_path.parent.mkdir(parents=True)
                    html_path.write_text("<html></html>")
                return SimpleNamespace(
                    returncode=0,
                    stdout=f"executed {script}",
                    stderr="",
                )

            with patch("scripts.run_workflow.subprocess.run", side_effect=run_step) as run:
                result = run_workflow(project_root, uploads)

            self.assertEqual(
                [
                    Path(call.args[0][-1]).relative_to(project_root).as_posix()
                    for call in run.call_args_list
                ],
                [script for _, script in PROCESSING_STEPS],
            )
            for key, filename in INPUT_FILES.items():
                self.assertEqual(
                    (project_root / "data" / "unprocessed" / filename).read_bytes(),
                    uploads[key],
                )
            self.assertEqual(result.html_path.read_text(), "<html></html>")
            self.assertEqual(len(result.processed_files), 5)
            self.assertIn("executed scripts/build_static_site.py", result.logs)

    def test_stops_when_a_pipeline_step_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            uploads = {key: b"workbook" for key in INPUT_FILES}

            def fail_on_delta(command, **_kwargs):
                self.assertEqual(_kwargs["cwd"], project_root)
                failed = Path(command[-1]).name == "analise_delta.py"
                return SimpleNamespace(
                    returncode=1 if failed else 0,
                    stdout="processor output",
                    stderr="invalid input" if failed else "",
                )

            with (
                patch(
                    "scripts.run_workflow.subprocess.run",
                    side_effect=fail_on_delta,
                ) as run,
                self.assertRaises(WorkflowStepError) as error,
            ):
                run_workflow(project_root, uploads)

            self.assertEqual(error.exception.step, "Análise de delta")
            self.assertIn("invalid input", str(error.exception))
            self.assertEqual(run.call_count, 2)

    def test_rejects_missing_uploads_before_writing_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                run_workflow(Path(temp_dir), {"tatica": b"workbook"})

            self.assertFalse((Path(temp_dir) / "data").exists())


if __name__ == "__main__":
    unittest.main()
