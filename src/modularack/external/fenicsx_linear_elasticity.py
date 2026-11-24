# SPDX-License-Identifier: AGPL-3.0-or-later
"""Linear elasticity on a given P1 tetrahedral mesh with nodal forces, solved in FEniCSx.

Runs inside the FEniCSx environment, not the Modularack one:
    micromamba run -n modularack-fenicsx python fenicsx_linear_elasticity.py problem.npz result.json

problem.npz holds points (N, 3), tets (E, 4), fixed (node indices), force_nodes and forces (K, 3),
modulus and poisson. The result is the largest displacement and the per-cell stress
(xx, yy, zz, xy, xz, yz), comparable with the CalculiX and scikit-fem P1 runs.
"""

import json
import sys

import basix.ufl
import numpy as np
import ufl
from dolfinx import fem, mesh
from dolfinx.fem.petsc import apply_lifting, assemble_matrix, assemble_vector, set_bc
from mpi4py import MPI
from petsc4py import PETSc

COORDINATE_DECIMALS = 6


def main() -> None:
    data = np.load(sys.argv[1])
    points = data["points"].astype(np.float64)
    cells = data["tets"].astype(np.int64)
    domain = mesh.create_mesh(MPI.COMM_SELF, cells, basix.ufl.element("Lagrange", "tetrahedron", 1, shape=(3,)), points)
    space = fem.functionspace(domain, ("Lagrange", 1, (3,)))
    coordinates = space.tabulate_dof_coordinates()
    lookup = {tuple(np.round(c, COORDINATE_DECIMALS)): i for i, c in enumerate(coordinates)}
    node_to_dof = np.array([lookup[tuple(np.round(p, COORDINATE_DECIMALS))] for p in points])

    modulus, poisson = float(data["modulus"]), float(data["poisson"])
    mu = modulus / (2 * (1 + poisson))
    lam = modulus * poisson / ((1 + poisson) * (1 - 2 * poisson))

    def sigma(u: ufl.Coefficient) -> ufl.core.expr.Expr:
        strain = ufl.sym(ufl.grad(u))
        return 2 * mu * strain + lam * ufl.tr(strain) * ufl.Identity(3)

    trial, test = ufl.TrialFunction(space), ufl.TestFunction(space)
    bilinear = fem.form(ufl.inner(sigma(trial), ufl.sym(ufl.grad(test))) * ufl.dx)
    zero = fem.Constant(domain, np.zeros(3))
    linear = fem.form(ufl.dot(zero, test) * ufl.dx)
    fixed_dofs = node_to_dof[data["fixed"]].astype(np.int32)
    bc = fem.dirichletbc(np.zeros(3), fixed_dofs, space)

    matrix = assemble_matrix(bilinear, bcs=[bc])
    matrix.assemble()
    vector = assemble_vector(linear)
    with vector.localForm() as local:
        array = local.array
        for node, force in zip(data["force_nodes"], data["forces"], strict=True):
            dof = node_to_dof[node]
            array[3 * dof : 3 * dof + 3] += force
    apply_lifting(vector, [bilinear], bcs=[[bc]])
    vector.ghostUpdate(addv=PETSc.InsertMode.ADD, mode=PETSc.ScatterMode.REVERSE)
    set_bc(vector, [bc])

    solver = PETSc.KSP().create(domain.comm)
    solver.setOperators(matrix)
    solver.setType("preonly")
    solver.getPC().setType("lu")
    displacement = fem.Function(space)
    solver.solve(vector, displacement.x.petsc_vec)
    displacement.x.scatter_forward()
    magnitude = float(np.sqrt((displacement.x.array.reshape(-1, 3) ** 2).sum(axis=1)).max())

    tensor_space = fem.functionspace(domain, ("DG", 0, (3, 3)))
    stress = fem.Function(tensor_space)
    stress.interpolate(fem.Expression(sigma(displacement), tensor_space.element.interpolation_points))
    s = stress.x.array.reshape(-1, 3, 3)
    rows = np.stack([s[:, 0, 0], s[:, 1, 1], s[:, 2, 2], s[:, 0, 1], s[:, 0, 2], s[:, 1, 2]], axis=-1)
    # dolfinx reorders cells; report them in the input's order, so each stress pairs with its element.
    ordered = np.empty_like(rows)
    ordered[domain.topology.original_cell_index] = rows
    rows = ordered
    with open(sys.argv[2], "w") as out:
        json.dump({"displacement": magnitude, "stresses": rows.tolist()}, out)


if __name__ == "__main__":
    main()
