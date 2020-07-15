
# Global imports
from pathlib import Path

from .topology import Bond, Angle, OFFProper, OFFImproper
from offpele.utils.toolkits import (AmberToolkitWrapper,
                                    RDKitToolkitWrapper,
                                    OpenForceFieldToolkitWrapper)
from .rotamer import MolecularGraph


class Atom(object):
    def __init__(self, index=-1, core=None, OPLS_type=None, PDB_name=None,
                 unknown=None, x=None, y=None, z=None, sigma=None,
                 epsilon=None, charge=None, born_radius=None, SASA_radius=None,
                 nonpolar_gamma=None, nonpolar_alpha=None, parent=None):
        self._index = index
        self._core = core
        self._OPLS_type = OPLS_type
        self._PDB_name = PDB_name
        self._unknown = unknown
        self._x = x
        self._y = y
        self._z = z
        self._sigma = sigma
        self._epsilon = epsilon
        self._charge = charge
        self._born_radius = born_radius  # Rad. Non Polar SGB
        self._SASA_radius = SASA_radius  # Rad. Non Polar Type
        self._nonpolar_gamma = nonpolar_gamma  # SGB Non Polar gamma
        self._nonpolar_alpha = nonpolar_alpha  # SGB Non Polar type
        self._parent = parent

    def set_index(self, index):
        self._index = index

    def set_as_core(self):
        self._core = True

    def set_as_branch(self):
        self._core = False

    def set_parent(self, parent):
        self._parent = parent

    def set_coords(self, coords):
        assert len(coords) == 3, '3D array is expected'

        self._x, self._y, self._z = coords

    @property
    def index(self):
        return self._index

    @property
    def core(self):
        return self._core

    @property
    def OPLS_type(self):
        return self._OPLS_type

    @property
    def PDB_name(self):
        return self._PDB_name

    @property
    def unknown(self):
        return self._unknown

    @property
    def x(self):
        return self._x

    @property
    def y(self):
        return self._y

    @property
    def z(self):
        return self._z

    @property
    def sigma(self):
        return self._sigma

    @property
    def epsilon(self):
        return self._epsilon

    @property
    def charge(self):
        return self._charge

    @property
    def born_radius(self):
        return self._born_radius

    @property
    def SASA_radius(self):
        return self._SASA_radius

    @property
    def nonpolar_gamma(self):
        return self._nonpolar_gamma

    @property
    def nonpolar_alpha(self):
        return self._nonpolar_alpha

    @property
    def parent(self):
        return self._parent


class DummyAtom(Atom):
    def __init__(self, index=-1, PDB_name='DUMM', parent=None):
        if parent is None:
            parent = self
        super().__init__(index, False, None, PDB_name, None, None, None, None,
                         None, None, None, None, None, None, None, parent)


class Molecule(object):
    def __init__(self, path=None):
        if isinstance(path, str):
            from pathlib import Path
            extension = Path(path).suffix
            extension = extension.strip('.')
            if extension == 'pdb':
                self._initialize_from_pdb(path)
            else:
                raise ValueError(
                    '{} is not a valid extension'.format(extension))
        else:
            self._initialize()

    def _initialize(self):
        self._name = ''
        self._forcefield = None
        self._atoms = list()
        self._bonds = list()
        self._angles = list()
        self._propers = list()
        self._OFF_propers = list()
        self._impropers = list()
        self._OFF_impropers = list()
        self._rdkit_molecule = None
        self._off_molecule = None
        self._rotamer_library = None
        self._graph = None

    def _initialize_from_pdb(self, path):
        self._initialize()
        print(' - Loading molecule from RDKit')

        rdkit_toolkit = RDKitToolkitWrapper()
        self._rdkit_molecule = rdkit_toolkit.from_pdb(path)

        # RDKit must generate stereochemistry specifically from 3D coords
        rdkit_toolkit.assign_stereochemistry_from_3D(self)

        # Set molecule name according to PDB's residue name
        name = rdkit_toolkit.get_residue_name(self)
        self.set_name(name)

        openforcefield_toolkit = OpenForceFieldToolkitWrapper()

        self._off_molecule = openforcefield_toolkit.from_rdkit(self)

    def set_name(self, name):
        if isinstance(name, str) and len(name) > 2:
            name = name[0:3].upper()
            self._name = name

            if self.off_molecule:
                self.off_molecule.name = name

    def parameterize(self, forcefield):
        if not self.off_molecule and not self.rdkit_molecule:
            raise Exception('OpenForceField molecule was not initialized '
                            + 'correctly')

        print(' - Loading forcefield')
        openforcefield_toolkit = OpenForceFieldToolkitWrapper()
        parameters = openforcefield_toolkit.get_parameters_from_forcefield(
            forcefield, self)

        self.parameters = parameters
        # TODO Is there a way to retrieve the name of the OFF's ForceField object?
        if isinstance(forcefield, str):
            self._forcefield = Path(forcefield).stem

        print(' - Computing partial charges with am1bcc')
        self._calculate_am1bcc_charges()

        self._build_atoms()

        self._build_bonds()

        self._build_angles()

        self._build_propers()

        self._build_impropers()

    def build_rotamer_library(self, resolution):
        self._assert_parameterized()

        print(' - Generating rotamer library')

        self._graph = MolecularGraph(self)

        self.graph.set_core()

        self.graph.set_parents()

        self._rotamer_library = self.graph.build_rotamer_library(resolution)

    def plot_rotamer_graph(self):
        self._assert_parameterized()

        try:
            from rdkit import Chem
        except ImportError:
            raise Exception('RDKit Python API not found')

        # Fins rotatable bond ids as in Lipinski module in RDKit
        # https://github.com/rdkit/rdkit/blob/1bf6ef3d65f5c7b06b56862b3fb9116a3839b229/rdkit/Chem/Lipinski.py#L47
        rot_bonds_atom_ids = self._rdkit_molecule.GetSubstructMatches(
            Chem.MolFromSmarts('[!$(*#*)&!D1]-&!@[!$(*#*)&!D1]'))

        graph = self._compute_rotamer_graph(rot_bonds_atom_ids)

        rot_edges = [(u, v) for (u, v, d) in graph.edges(data=True)
                     if d['weight'] == 1]
        nrot_edges = [(u, v) for (u, v, d) in graph.edges(data=True)
                      if d['weight'] == 0]

        import networkx as nx

        pos = nx.circular_layout(graph)

        nx.draw_networkx_nodes(graph, pos, node_size=400)
        nx.draw_networkx_edges(graph, pos, edgelist=rot_edges,
                               width=4)
        nx.draw_networkx_edges(graph, pos, edgelist=nrot_edges,
                               width=4, alpha=0.5, edge_color='b',
                               style='dashed')
        nx.draw_networkx_labels(graph, pos, font_size=10,
                                font_family='sans-serif')

        import matplotlib.pyplot as plt
        plt.axis('off')
        plt.show()

    def _assert_parameterized(self):
        try:
            assert self.off_molecule is not None
        except AssertionError:
            raise Exception('Molecule not parameterized')

    def _calculate_am1bcc_charges(self):
        amber_toolkit = AmberToolkitWrapper()

        charges = amber_toolkit.compute_partial_charges_am1bcc(self)

        self.off_molecule.partial_charges = charges

    def _build_atoms(self):
        # PELE needs underscores instead of whitespaces
        pdb_atom_names = {(i, ): name.replace(' ', '_',)
                          for i, name in enumerate(self.get_pdb_atom_names())}

        # TODO should we assign an OPLS type? How can we do this with OFF?
        OPLS_types = {i: None
                      for i in self.parameters.get_vdW_parameters().keys()}

        # TODO Which is the purpose of unknown value? Is it important?
        unknowns = {i: None
                    for i in self.parameters.get_vdW_parameters().keys()}

        # TODO Create z-matrix from 3D coordinates

        coords = RDKitToolkitWrapper().get_coordinates(self)

        sigmas = self.parameters.get_vdW_sigmas()

        if all([sigma is None for sigma in sigmas.values()]):
            sigmas = self.parameters.get_vdW_sigmas_from_rmin_halves()

        epsilons = self.parameters.get_vdW_epsilons()

        # TODO Find a way to assign implicit solvent parameters to atoms with OFF
        born_radii = {i: None
                      for i in self.parameters.get_vdW_parameters().keys()}

        # TODO Doublecheck later this relation
        SASA_radii = {i: j / 2.0 for i, j in sigmas.items()}

        # TODO Find a way to assign implicit solvent parameters to atoms with OFF
        nonpolar_gammas = {i: None for i in
                           self.parameters.get_vdW_parameters().keys()}
        nonpolar_alphas = {i: None for i in
                           self.parameters.get_vdW_parameters().keys()}

        for index in self.parameters.get_vdW_parameters().keys():
            assert len(index) == 1, 'Index should be a tupple of length 1'
            atom = Atom(index=int(index[0]),
                        PDB_name=pdb_atom_names[index],
                        OPLS_type=OPLS_types[index],
                        unknown=unknowns[index],
                        x=coords[index][0],
                        y=coords[index][1],
                        z=coords[index][2],
                        sigma=sigmas[index],
                        epsilon=epsilons[index],
                        charge=self.off_molecule.partial_charges[index],
                        born_radius=born_radii[index],
                        SASA_radius=SASA_radii[index],
                        nonpolar_gamma=nonpolar_gammas[index],
                        nonpolar_alpha=nonpolar_alphas[index])
            self._add_atom(atom)

    def _add_atom(self, atom):
        self._atoms.append(atom)

    def _build_bonds(self):
        lengths = self.parameters.get_bond_lengths()

        ks = self.parameters.get_bond_ks()

        bond_indexes = self.parameters.get_bond_parameters().keys()

        for index, atom_indexes in enumerate(bond_indexes):
            (atom1_idx, atom2_idx) = atom_indexes
            bond = Bond(index=index, atom1_idx=atom1_idx, atom2_idx=atom2_idx,
                        spring_constant=ks[atom_indexes],
                        eq_dist=lengths[atom_indexes])
            self._add_bond(bond)

    def _add_bond(self, bond):
        self._bonds.append(bond)

    def _build_angles(self):
        angles = self.parameters.get_angle_angles()

        ks = self.parameters.get_angle_ks()

        angle_indexes = self.parameters.get_angle_parameters().keys()

        for index, atom_indexes in enumerate(angle_indexes):
            atom1_idx, atom2_idx, atom3_idx = atom_indexes
            angle = Angle(index=index, atom1_idx=atom1_idx,
                          atom2_idx=atom2_idx, atom3_idx=atom3_idx,
                          spring_constant=ks[atom_indexes],
                          eq_angle=angles[atom_indexes])
            self._add_angle(angle)

    def _add_angle(self, angle):
        self._angles.append(angle)

    def _build_propers(self):
        periodicities = self.parameters.get_dihedral_periodicities()
        phases = self.parameters.get_dihedral_phases()
        ks = self.parameters.get_dihedral_ks()
        idivfs = self.parameters.get_dihedral_idivfs()

        # idivf is a optional parameter in OpenForceField
        if len(idivfs) == 0:
            for period_by_index in periodicities:
                idivfs.append(dict(zip(period_by_index.keys(),
                                       [1, ] * len(period_by_index.keys()))))

        assert len(periodicities) == len(phases) and \
            len(periodicities) == len(ks) and \
            len(periodicities) == len(idivfs), 'Unconsistent set of ' \
            'OpenForceField\'s torsional parameters. They all should have ' \
            'equal lengths'

        for period_by_index, phase_by_index, k_by_index, idivf_by_index in \
                zip(periodicities, phases, ks, idivfs):

            assert period_by_index.keys() == phase_by_index.keys() and \
                period_by_index.keys() == k_by_index.keys() and \
                period_by_index.keys() == idivf_by_index.keys(), 'Unconsistent ' \
                'torsional parameter indexes. Keys should match.'

            for index in period_by_index.keys():
                atom1_idx, atom2_idx, atom3_idx, atom4_idx = index

                period = period_by_index[index]
                phase = phase_by_index[index]
                k = k_by_index[index]
                idivf = idivf_by_index[index]

                if period and phase and k and idivf:
                    off_proper = OFFProper(atom1_idx=atom1_idx,
                                           atom2_idx=atom2_idx,
                                           atom3_idx=atom3_idx,
                                           atom4_idx=atom4_idx,
                                           periodicity=period,
                                           phase=phase,
                                           k=k,
                                           idivf=idivf)

                    PELE_proper = off_proper.to_PELE()
                    self._add_proper(PELE_proper)
                    self._add_OFF_proper(off_proper)

    def _add_proper(self, proper):
        self._propers.append(proper)

    def _add_OFF_proper(self, proper):
        self._OFF_propers.append(proper)

    def _build_impropers(self):
        periodicities = self.parameters.get_improper_periodicities()
        phases = self.parameters.get_improper_phases()
        ks = self.parameters.get_improper_ks()
        idivfs = self.parameters.get_improper_idivfs()

        # idivf is a optional parameter in OpenForceField
        if len(idivfs) == 0:
            for period_by_index in periodicities:
                idivfs.append(dict(zip(period_by_index.keys(),
                                       [1, ] * len(period_by_index.keys()))))

        assert len(periodicities) == len(phases) and \
            len(periodicities) == len(ks) and \
            len(periodicities) == len(idivfs), 'Unconsistent set of ' \
            'OpenForceField\'s improper parameters. They all should have ' \
            'equal lengths'

        for period_by_index, phase_by_index, k_by_index, idivf_by_index in \
                zip(periodicities, phases, ks, idivfs):

            assert period_by_index.keys() == phase_by_index.keys() and \
                period_by_index.keys() == k_by_index.keys() and \
                period_by_index.keys() == idivf_by_index.keys(), 'Unconsistent ' \
                'torsional parameter indexes. Keys should match.'

            for index in period_by_index.keys():
                atom1_idx, atom2_idx, atom3_idx, atom4_idx = index

                period = period_by_index[index]
                phase = phase_by_index[index]
                k = k_by_index[index]
                idivf = idivf_by_index[index]

                if period and phase and k and idivf:
                    off_improper = OFFImproper(atom1_idx=atom1_idx,
                                               atom2_idx=atom2_idx,
                                               atom3_idx=atom3_idx,
                                               atom4_idx=atom4_idx,
                                               periodicity=period,
                                               phase=phase,
                                               k=k,
                                               idivf=idivf)

                    PELE_improper = off_improper.to_PELE()
                    self._add_improper(PELE_improper)
                    self._add_OFF_improper(off_improper)

    def _add_improper(self, improper):
        self._impropers.append(improper)

    def _add_OFF_improper(self, improper):
        self._OFF_impropers.append(improper)

    def get_pdb_atom_names(self):
        self._assert_parameterized()

        pdb_atom_names = list()

        for atom in self.rdkit_molecule.GetAtoms():
            pdb_info = atom.GetPDBResidueInfo()
            pdb_atom_names.append(pdb_info.GetName())

        return pdb_atom_names

    def to_impact(self, path):
        pass

    @property
    def off_molecule(self):
        return self._off_molecule

    @property
    def rdkit_molecule(self):
        return self._rdkit_molecule

    @property
    def rotamer_library(self):
        return self._rotamer_library

    @property
    def name(self):
        return self._name

    @property
    def forcefield(self):
        return self._forcefield

    @property
    def atoms(self):
        return self._atoms

    @property
    def bonds(self):
        return self._bonds

    @property
    def angles(self):
        return self._angles

    @property
    def propers(self):
        return self._propers

    @property
    def impropers(self):
        return self._impropers

    @property
    def graph(self):
        return self._graph
