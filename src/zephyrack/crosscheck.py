# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run one linear-elastic problem through independent FE codes so they can be compared.

Every runner gets the identical P1 tetrahedral mesh, supports and nodal forces taken from an
`EarProblem`, and returns the largest displacement and stress rows (xx, yy, zz, xy, xz, yz):

- CalculiX (C3D4) and scikit-fem (P1), in `fea.py`;
- FEniCSx (dolfinx), in its own micromamba environment;
- Code_Aster, in the simvia/code_aster container;
- Elmer, in the openeuler/elmer container.

FEniCSx, Code_Aster and scikit-fem report per-element stress; Elmer reports nodal (averaged)
stress, so its stress percentiles are compared more loosely than its displacement.
"""

from __future__ import annotations

import json
import os
import subprocess
import xml.etree.ElementTree as ElementTree
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .fea import PLA, SOLVER_TIMEOUT, EarProblem, Material

MICROMAMBA = os.environ.get("ZEPHYRACK_MICROMAMBA", "micromamba")
FENICSX_ENV = os.environ.get("ZEPHYRACK_FENICSX_ENV", "zephyrack-fenicsx")
CODE_ASTER_IMAGE = os.environ.get("ZEPHYRACK_CODE_ASTER_IMAGE", "docker.io/simvia/code_aster:stable")
ELMER_IMAGE = os.environ.get("ZEPHYRACK_ELMER_IMAGE", "docker.io/openeuler/elmer:latest")
CONTAINER_WORKDIR = "/work"
FENICSX_SCRIPT = Path(__file__).parent / "external" / "fenicsx_linear_elasticity.py"

Solution = tuple[float, list[tuple[float, ...]]]


@dataclass
class LinearProblem:
    """The P1 view of an EarProblem: 0-based corner nodes, tets, fixed nodes and nodal forces."""

    points: np.ndarray
    tets: np.ndarray
    fixed: np.ndarray
    force_nodes: np.ndarray
    forces: np.ndarray

    @classmethod
    def of(cls, problem: EarProblem) -> LinearProblem:
        corners = sorted(problem.corners())
        index = {n: k for k, n in enumerate(corners)}
        forces = problem.nodal_forces(set(corners))
        return cls(
            points=np.array([problem.nodes[n] for n in corners], dtype=float),
            tets=np.array([[index[n] for n in e[:4]] for e in problem.elements], dtype=np.int64),
            fixed=np.array(sorted(index[n] for n in problem.fixed if n in index), dtype=np.int64),
            force_nodes=np.array([index[n] for n in forces], dtype=np.int64),
            forces=np.array(list(forces.values()), dtype=float),
        )

    def force_groups(self) -> list[tuple[tuple[float, float, float], list[int]]]:
        """Nodes grouped by identical force vector, for codes that load named node groups."""
        groups: dict[tuple[float, float, float], list[int]] = defaultdict(list)
        for node, force in zip(self.force_nodes, self.forces, strict=True):
            groups[(float(force[0]), float(force[1]), float(force[2]))].append(int(node))
        return list(groups.items())


def _num(value: float) -> str:
    """A plain decimal for solver input files (repr of a numpy float would print np.float64(...))."""
    return f"{float(value):.12g}"


def _run(command: list[str], cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=SOLVER_TIMEOUT)
    if result.returncode != 0:
        raise RuntimeError(f"{command[0]} failed ({result.returncode}): {result.stdout[-2000:]}{result.stderr[-2000:]}")


def run_fenicsx(problem: LinearProblem, work: Path, material: Material = PLA) -> Solution:
    np.savez(
        work / "problem.npz",
        points=problem.points,
        tets=problem.tets,
        fixed=problem.fixed,
        force_nodes=problem.force_nodes,
        forces=problem.forces,
        modulus=material.modulus,
        poisson=material.poisson,
    )
    _run([MICROMAMBA, "run", "-n", FENICSX_ENV, "python", str(FENICSX_SCRIPT), "problem.npz", "fenicsx.json"], work)
    result = json.loads((work / "fenicsx.json").read_text())
    return float(result["displacement"]), [tuple(row) for row in result["stresses"]]


def _podman(image: str, work: Path, script: str) -> list[str]:
    return ["podman", "run", "--rm", "--user", "0", "-v", f"{work}:{CONTAINER_WORKDIR}:Z", image, "bash", "-c", script]


def run_code_aster(problem: LinearProblem, work: Path, material: Material = PLA) -> Solution:
    groups = problem.force_groups()
    mesh = ["COOR_3D"] + [f"N{i + 1} {_num(x)} {_num(y)} {_num(z)}" for i, (x, y, z) in enumerate(problem.points)]
    mesh.append("FINSF")
    mesh += ["TETRA4"] + [f"M{i + 1} " + " ".join(f"N{n + 1}" for n in t) for i, t in enumerate(problem.tets)]
    mesh += ["FINSF", "GROUP_NO", "FIXED"] + [f"N{n + 1}" for n in problem.fixed] + ["FINSF"]
    for k, (_, nodes) in enumerate(groups):
        mesh += ["GROUP_NO", f"F{k}"] + [f"N{n + 1}" for n in nodes] + ["FINSF"]
    mesh.append("FIN")
    (work / "ear.mail").write_text("\n".join(mesh) + "\n")
    loads = ",\n        ".join(
        f"_F(GROUP_NO='F{k}', FX={fx!r}, FY={fy!r}, FZ={fz!r})" for k, ((fx, fy, fz), _) in enumerate(groups)
    )
    (work / "ear.comm").write_text(
        f"""DEBUT(LANG='EN')
mesh = LIRE_MAILLAGE(FORMAT='ASTER', UNITE=20)
model = AFFE_MODELE(MAILLAGE=mesh, AFFE=_F(TOUT='OUI', PHENOMENE='MECANIQUE', MODELISATION='3D'))
mat = DEFI_MATERIAU(ELAS=_F(E={material.modulus!r}, NU={material.poisson!r}))
field = AFFE_MATERIAU(MAILLAGE=mesh, AFFE=_F(TOUT='OUI', MATER=mat))
load = AFFE_CHAR_MECA(
    MODELE=model,
    DDL_IMPO=_F(GROUP_NO='FIXED', DX=0.0, DY=0.0, DZ=0.0),
    FORCE_NODALE=(
        {loads},
    ),
)
res = MECA_STATIQUE(MODELE=model, CHAM_MATER=field, EXCIT=_F(CHARGE=load))
res = CALC_CHAMP(reuse=res, RESULTAT=res, CONTRAINTE='SIGM_ELGA')
disp = CREA_TABLE(RESU=_F(RESULTAT=res, NOM_CHAM='DEPL', TOUT='OUI', NOM_CMP=('DX', 'DY', 'DZ')))
stress = CREA_TABLE(
    RESU=_F(RESULTAT=res, NOM_CHAM='SIGM_ELGA', TOUT='OUI', NOM_CMP=('SIXX', 'SIYY', 'SIZZ', 'SIXY', 'SIXZ', 'SIYZ'))
)
IMPR_TABLE(TABLE=disp, UNITE=30, FORMAT='TABLEAU', NOM_PARA=('DX', 'DY', 'DZ'))
IMPR_TABLE(TABLE=stress, UNITE=31, FORMAT='TABLEAU', NOM_PARA=('SIXX', 'SIYY', 'SIZZ', 'SIXY', 'SIXZ', 'SIYZ'))
FIN()
"""
    )
    w = CONTAINER_WORKDIR
    (work / "ear.export").write_text(
        f"""P time_limit {SOLVER_TIMEOUT}
P memory_limit 4096
F comm {w}/ear.comm D 1
F mail {w}/ear.mail D 20
F libr {w}/displacement.txt R 30
F libr {w}/stress.txt R 31
F mess {w}/ear.mess R 6
"""
    )
    _run(_podman(CODE_ASTER_IMAGE, work, f"source /opt/activate.sh && run_aster {w}/ear.export"), work)
    displacement = max((float(np.linalg.norm(row)) for row in _table(work / "displacement.txt", 3)), default=0.0)
    return displacement, [tuple(row) for row in _table(work / "stress.txt", 6)]


def _table(path: Path, columns: int) -> list[list[float]]:
    """Numeric rows of a Code_Aster TABLEAU print, skipping its headers."""
    rows = []
    for line in path.read_text().splitlines():
        fields = line.split()
        if len(fields) != columns:
            continue
        try:
            rows.append([float(f.replace("D", "E")) for f in fields])
        except ValueError:
            continue
    return rows


def run_elmer(problem: LinearProblem, work: Path, material: Material = PLA) -> Solution:
    mesh_dir = work / "mesh"
    mesh_dir.mkdir(exist_ok=True)
    nodes, elements = len(problem.points), len(problem.tets)
    (mesh_dir / "mesh.header").write_text(f"{nodes} {elements} 0\n1\n504 {elements}\n")
    (mesh_dir / "mesh.nodes").write_text(
        "".join(f"{i + 1} -1 {_num(x)} {_num(y)} {_num(z)}\n" for i, (x, y, z) in enumerate(problem.points))
    )
    (mesh_dir / "mesh.elements").write_text(
        "".join(f"{i + 1} 1 504 " + " ".join(str(n + 1) for n in t) + "\n" for i, t in enumerate(problem.tets))
    )
    (mesh_dir / "mesh.boundary").write_text("")

    def target(nodes_list: list[int]) -> str:
        return f"  Target Nodes({len(nodes_list)}) = " + " ".join(str(n + 1) for n in nodes_list)

    conditions = [
        "Boundary Condition 1\n"
        + target([int(n) for n in problem.fixed])
        + "\n  Displacement 1 = 0\n  Displacement 2 = 0\n  Displacement 3 = 0\nEnd"
    ]
    for k, ((fx, fy, fz), group) in enumerate(problem.force_groups()):
        conditions.append(
            f"Boundary Condition {k + 2}\n{target(group)}\n"
            # Nodal loads aren't predefined keywords, so Elmer needs their type spelled out.
            f"  Displacement 1 Load = Real {fx!r}\n  Displacement 2 Load = Real {fy!r}\n"
            f"  Displacement 3 Load = Real {fz!r}\nEnd"
        )
    (work / "ear.sif").write_text(
        f"""Header
  Mesh DB "." "mesh"
End
Simulation
  Coordinate System = Cartesian 3D
  Simulation Type = Steady
  Steady State Max Iterations = 1
  Output Intervals = 1
End
Body 1
  Equation = 1
  Material = 1
End
Equation 1
  Active Solvers(2) = 1 2
End
Material 1
  Youngs Modulus = {material.modulus!r}
  Poisson Ratio = {material.poisson!r}
End
Solver 1
  Equation = Linear elasticity
  Procedure = "StressSolve" "StressSolver"
  Variable = -dofs 3 Displacement
  Calculate Stresses = True
  Linear System Solver = Direct
  Linear System Direct Method = UMFPACK
End
Solver 2
  Equation = Output
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = ear
  Output Format = vtu
  Ascii Output = True
  Exec Solver = After Simulation
End
"""
        + "\n".join(conditions)
        + "\n"
    )
    (work / "ELMERSOLVER_STARTINFO").write_text("ear.sif\n1\n")
    _run(_podman(ELMER_IMAGE, work, f"cd {CONTAINER_WORKDIR} && ElmerSolver ear.sif"), work)
    return _read_vtu(next(work.glob("**/ear*.vtu")))


ELMER_STRESS_ARRAYS = ("stress_xx", "stress_yy", "stress_zz", "stress_xy", "stress_xz", "stress_yz")
"""Elmer's VTU output names each nodal stress component separately."""


def _read_vtu(path: Path) -> Solution:
    arrays: dict[str, np.ndarray] = {}
    for array in ElementTree.parse(path).getroot().iter("DataArray"):
        name = array.get("Name", "")
        components = int(array.get("NumberOfComponents", "1"))
        values = np.array(array.text.split(), dtype=float) if array.text else np.array([])
        arrays[name.lower()] = values.reshape(-1, components)
    displacement = arrays["displacement"]
    magnitude = float(np.sqrt((displacement**2).sum(axis=1)).max())
    stress = np.hstack([arrays[name] for name in ELMER_STRESS_ARRAYS])
    return magnitude, [tuple(float(v) for v in row) for row in stress]
