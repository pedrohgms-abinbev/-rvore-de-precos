from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Arquivos obrigatórios enviados pelo usuário.
INPUT_FILES = {
    "tatica": "10. Tatica Cerveja.xlsx",
    "ctr": "CTR - Árvore de Preços.xlsx",
    "calendario": "Calendario Direta Outubro.xlsx",
    "repasse": "Repasse.xlsb",
}

# Fonte opcional para atualizar o TTC Tática de AC e RO.
# Se não for enviada pelo formulário, o workflow utilizará o arquivo que já
# estiver em data/unprocessed, caso exista.
OPTIONAL_INPUT_FILES = {
    "arvore_politica": "Árvore Cerveja - Setembro 26 Atualizada.xlsx",
}

PROCESSING_STEPS = (
    ("Tratamento da Tática", "src/tratamento_tatica.py"),
    # Deve rodar imediatamente depois da geração de tatica_arvore.csv e antes
    # das análises/consolidações que utilizam os preços da Tática.
    ("Atualização TTC Tática de AC e RO", "src/atualizar_ac_ro_tatica_arvore.py"),
    ("Análise de delta", "src/analise_delta.py"),
    ("Tratamento do Calendário", "src/tratamento_calendario.py"),
    ("Tratamento do CTR", "src/tratamento_ctr.py"),
    ("Tratamento do Repasse", "scripts/gerar_repasse.py"),
    ("Consolidação da árvore", "src/consolidacao.py"),
    ("Geração do site HTML", "scripts/build_static_site.py"),
)

PROCESSED_FILES = (
    "tatica_arvore.csv",
    "tatica_delta.csv",
    "calendario_arvore.csv",
    "ctr_arvore.csv",
    "arvore_precos.csv",
    "repasse.csv",
)


@dataclass(frozen=True)
class WorkflowResult:
    html_path: Path
    processed_files: tuple[Path, ...]
    logs: str


class WorkflowStepError(RuntimeError):
    def __init__(self, step: str, output: str) -> None:
        self.step = step
        self.output = output
        details = output.strip() or "O comando não informou detalhes adicionais."
        super().__init__(f"A etapa '{step}' falhou.\n{details}")


def run_workflow(project_root: Path) -> WorkflowResult:
    root = project_root.resolve()
    unprocessed_dir = root / "data" / "unprocessed"
    unprocessed_dir.mkdir(parents=True, exist_ok=True)

    missing = [
        str(unprocessed_dir / filename)
        for filename in INPUT_FILES.values()
        if not (unprocessed_dir / filename).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Arquivos de entrada não encontrados em data/unprocessed: "
            + "; ".join(missing)
        )

    step_logs: list[str] = []
    for label, script in PROCESSING_STEPS:
        script_path = root / script
        if not script_path.is_file():
            output = f"Script não encontrado: {script_path}"
            step_logs.append(f"## {label}\n{output}")
            raise WorkflowStepError(label, output)

        completed = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        output = "\n".join(
            part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
        )
        step_logs.append(f"## {label}\n{output or 'Concluído.'}")
        if completed.returncode != 0:
            raise WorkflowStepError(label, output)

    processed_dir = root / "data" / "processed"
    processed_files = tuple(processed_dir / name for name in PROCESSED_FILES)
    missing_outputs = [str(path) for path in processed_files if not path.is_file()]
    html_path = root / "site-premium" / "arvore_precos_premium.html"

    if missing_outputs:
        raise FileNotFoundError(
            "O pipeline terminou sem gerar todos os arquivos processados: "
            + ", ".join(missing_outputs)
        )
    if not html_path.is_file():
        raise FileNotFoundError(f"O HTML premium não foi gerado: {html_path}")

    return WorkflowResult(
        html_path=html_path,
        processed_files=processed_files,
        logs="\n\n".join(step_logs),
    )


if __name__ == "__main__":
    result = run_workflow(Path(__file__).resolve().parents[1])
    print(result.html_path)
