# (c) 2015-2018 Acellera Ltd http://www.acellera.com
# All Rights Reserved
# Distributed under HTMD Software License Agreement
# No redistribution in whole or part
#
import numpy as np
from moleculekit.util import tempname, ensurelist
from copy import deepcopy
from os import path
import logging
import os
import abc

logger = logging.getLogger(__name__)


class TopologyInconsistencyError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


_residueNameTable = {
    'ARG': 'R', 'AR0': 'R',
    'HIS': 'H', 'HID': 'H', 'HIE': 'H', 'HIP': 'H', 'HSD': 'H', 'HSE': 'H', 'HSP': 'H',
    'LYS': 'K', 'LSN': 'K', 'LYN': 'K',
    'ASP': 'D', 'ASH': 'D',
    'GLU': 'E', 'GLH': 'E',
    'SER': 'S',
    'THR': 'T',
    'ASN': 'N',
    'GLN': 'Q',
    'CYS': 'C', 'CYX': 'C',
    'SEC': 'U',
    'GLY': 'G',
    'PRO': 'P',
    'ALA': 'A',
    'VAL': 'V',
    'ILE': 'I',
    'LEU': 'L',
    'MET': 'M',
    'PHE': 'F',
    'TYR': 'Y',
    'TRP': 'W'
}

_modResidueNameTable = {
    'MLZ': 'K', 'MLY': 'K',
    'MSE': 'M'
}


class Molecule(object):
    """
    Class to manipulate molecular structures.

    Molecule contains all the fields of a PDB and it is independent of any force field. It can contain multiple
    conformations and trajectories, however all operations are done on the current frame. The following PDB fields 
    are accessible as attributes (record, serial, name, altloc, resname, chain, resid, insertion, coords,
    occupancy, beta, segid, element, charge). The coordinates are accessible via the coords attribute 
    ([number of atoms x 3 x number of frames] where [x,y,z] are the second dimension.

    Parameters
    ----------
    filename : str or list of str
            Optionally load a PDB file from the specified file. If there's no file and the value is four characters long
            assume it is a PDB accession code and try to download from the RCSB web server.
    name : str
        Give a name to the Molecule that will be used for visualization
    kwargs :
        Accepts any further arguments that should be passed to the Molecule.read method.

    Examples
    --------
    >>> mol = Molecule( './test/data/dhfr/dhfr.pdb' )  # doctest: +SKIP
    >>> mol = Molecule( '3PTB', name='Trypsin' )
    >>> print(mol)                                     # doctest: +ELLIPSIS
    Molecule with 1701 atoms and 1 frames
    Atom field - altloc shape: (1701,)
    Atom field - atomtype shape: (1701,)
    ...

    .. rubric:: Methods
    .. autoautosummary:: moleculekit.molecule.Molecule
       :methods:
       
    .. rubric:: Attributes

    Attributes
    ----------
    
    numAtoms : int
        Number of atoms in the Molecule
    numFrames : int
        Number of conformers / simulation frames in the Molecule
    numResidues : int
        Number of residues in the Molecule

    record : np.ndarray
        The record field of a PDB file if the topology was read from a PDB.
    serial : np.ndarray
        The serial number of each atom.
    name : np.ndarray
        The name of each atom.
    altloc : np.ndarray
        The alternative location flag of the atoms if read from a PDB.
    resname : np.ndarray
        The residue name of each atom.
    chain : np.ndarray
        The chain name of each atom.
    resid : np.ndarray
        The residue ID of each atom.
    insertion : np.ndarray
        The insertion flag of the atoms if read from a PDB.
    occupancy : np.ndarray
        The occupancy value of each atom if read from a PDB.
    beta : np.ndarray
        The beta factor value of each atom if read from a PDB.
    segid : np.ndarray
        The segment ID of each atom.
    element : np.ndarray
        The element of each atom.
    charge : np.ndarray
        The charge of each atom.
    masses : np.ndarray
        The mass of each atom.
    atomtype : np.ndarray
        The atom type of each atom.

    coords : np.ndarray
        A float32 array with shape (natoms, 3, nframes) containing the coordinates of the Molecule.
    box : np.ndarray
        A float32 array with shape (3, nframes) containing the periodic box dimensions of an MD trajectory.
    boxangles : np.ndarray
        The angles of the box. If none are set they are assumed to be 90 degrees.

    bonds : np.ndarray
        Atom pairs corresponding to bond terms.
    bondtype : np.ndarray
        The type of each bond in `Molecule.bonds` if available.
    angles : np.ndarray
        Atom triplets corresponding to angle terms.
    dihedrals : np.ndarray
        Atom quadruplets corresponding to dihedral terms.
    impropers : np.ndarray
        Atom quadruplets corresponding to improper dihedral terms.

    crystalinfo : dict
        A dictionary containing crystallographic information. It has fields ['sGroup', 'numcopies', 'rotations', 'translations']

    frame : int
        The current frame. atomselection and get commands will be calculated on this frame.
    fileloc : list
        The location of the files used to read this Molecule
    time : list
        The time for each frame of the simulation
    fstep : list
        The step for each frame of the simulation
    reps : :class:`Representations` object
        A list of representations that is used when visualizing the molecule
    viewname : str
        The name used for the molecule in the viewer

    """
    _atom_fields = ('record', 'serial', 'name', 'altloc', 'resname', 'chain', 'resid', 'insertion',
                   'occupancy', 'beta', 'segid', 'element', 'charge', 'masses', 'atomtype')
    _connectivity_fields = ('bonds', 'bondtype', 'angles', 'dihedrals', 'impropers')
    _topo_fields = tuple(list(_atom_fields) + list(_connectivity_fields) + ['crystalinfo',])
    _traj_fields = ('coords', 'box', 'boxangles', 'fileloc', 'step', 'time')
    _atom_and_coord_fields = tuple(list(_atom_fields) + ['coords', ])

    _dtypes = {
        'record': object,
        'serial': np.int,
        'name': object,
        'altloc': object,
        'resname': object,
        'chain': object,
        'resid': np.int,
        'insertion': object,
        'coords': np.float32,
        'occupancy': np.float32,
        'beta': np.float32,
        'segid': object,
        'element': object,
        'charge': np.float32,
        'bonds': np.uint32,
        'angles': np.uint32,
        'dihedrals': np.uint32,
        'impropers': np.uint32,
        'atomtype': object,
        'bondtype': object,
        'masses': np.float32,
        'box': np.float32,
        'boxangles': np.float32
    }

    _dims = {
        'record': (0,),
        'serial': (0,),
        'name': (0,),
        'altloc': (0,),
        'resname': (0,),
        'chain': (0,),
        'resid': (0,),
        'insertion': (0,),
        'coords': (0, 3, 0),
        'occupancy': (0,),
        'beta': (0,),
        'segid': (0,),
        'element': (0,),
        'charge': (0,),
        'bonds': (0, 2),
        'angles': (0, 3),
        'dihedrals': (0, 4),
        'impropers': (0, 4),
        'atomtype': (0,),
        'bondtype': (0,),
        'masses': (0,),
        'box': (3, 0),
        'boxangles': (3, 0),
    }

    def __init__(self, filename=None, name=None, **kwargs):
        for field in self._dtypes:
            self.__dict__[field] = np.empty(self._dims[field], dtype=self._dtypes[field])
        self.ssbonds = []
        self._frame = 0
        self.fileloc = []
        self.time = []
        self.step = []
        self.crystalinfo = None

        self.reps = Representations(self)
        self._tempreps = Representations(self)
        self.viewname = name

        if filename is not None:
            self.read(filename, **kwargs)

    @staticmethod
    def _empty(numAtoms, field):
        dims = list(Molecule._dims[field])
        dims[0] = numAtoms
        data = np.zeros(dims, dtype=Molecule._dtypes[field])
        if Molecule._dtypes[field] is object:
            data[:] = ''
        if field == 'record':
            data[:] = 'ATOM'
        if field == 'serial':
            data = np.arange(1, numAtoms + 1)
        return data

    @property
    def fstep(self):
        """ The frame-step of the trajectory """
        if self.time is not None and len(self.time) > 1:
            uqf, uqidx = np.unique([f[0] for f in self.fileloc], return_inverse=True)
            diff = None
            for f, n in enumerate(uqf):
                df = np.unique(np.diff(self.time[uqidx == f]))
                if len(df) != 1:
                    logger.warning('Different timesteps in Molecule.time for file {}. Cannot calculate fstep.'.format(n))
                    return None
                if diff is None:
                    diff = df
                if df != diff:
                    logger.warning('Different timesteps detected between files {} and {}. Cannot calculate fstep.'.format(uqf[f], uqf[f-1]))
            if diff is not None:
                return float(diff / 1E6)  # convert femtoseconds to nanoseconds
            else:
                return None
        return None

    @property
    def frame(self):
        """ The currently active frame of the Molecule on which methods will be applied """
        if self._frame < 0 or self._frame >= self.numFrames:
            raise NameError("frame out of range")
        return self._frame

    @frame.setter
    def frame(self, value):
        if value < 0 or ((self.numFrames != 0) and (value >= self.numFrames)):
            raise NameError("Frame index out of range. Molecule contains {} frame(s). Frames are 0-indexed.".format(self.numFrames))
        self._frame = value

    @property
    def numResidues(self):
        """ The number of residues in the Molecule """
        from moleculekit.util import sequenceID
        return len(np.unique(sequenceID((self.resid, self.insertion, self.chain))))

    def insert(self, mol, index, collisions=0, coldist=1.3):
        """Insert the atoms of one molecule into another at a specific index.

        Parameters
        ----------
        mol   : :class:`Molecule`
                Molecule to be inserted
        index : integer
                The atom index at which the passed molecule will be inserted
        collisions : bool
            If set to True it will remove residues of `mol` which collide with atoms of this Molecule object.
        coldist : float
            Collision distance in Angstrom between atoms of the two molecules. Anything closer will be considered a collision.

        Example
        -------
        >>> mol=tryp.copy()
        >>> mol.numAtoms
        1701
        >>> mol.insert(tryp, 0)
        >>> mol.numAtoms
        3402
        """
        def insertappend(index, data1, data2, append):
            if not isinstance(data1, np.ndarray):
                data1 = np.array([data1])
            if not isinstance(data2, np.ndarray):
                data2 = np.array([data2])
            if data1.size == 0:
                return data2
            if data2.size == 0:
                return data1
            if append:  # TODO: Remove this if numpy insert is as fast as append
                return np.append(data1, data2, axis=0)
            else:
                return np.insert(data1, index, data2, axis=0)
        append = index == self.numAtoms

        if collisions:
            idx1, idx2 = _detectCollisions(self, self.frame, mol, mol.frame, coldist)
            torem, numres = _getResidueIndexesByAtom(mol, idx2)
            mol = mol.copy()
            logger.info('Removed {} residues from appended Molecule due to collisions.'.format(numres))
            mol.remove(torem, _logger=False)

        backup = self.copy()
        try:
            mol.coords = np.atleast_3d(mol.coords)  # Ensuring 3D coords for appending
            # TODO: Why this limitation?
            if np.size(self.coords) != 0 and (np.size(self.coords, 2) != 1 or np.size(mol.coords, 2) != 1):
                raise NameError('Cannot concatenate molecules which contain multiple frames.')

            if len(self.bonds) > 0:
                self.bonds[self.bonds >= index] += mol.numAtoms
            if len(mol.bonds) > 0:
                newbonds = mol.bonds.copy()
                newbonds += index
                if len(self.bonds) > 0:
                    self.bonds = np.append(self.bonds, newbonds, axis=0)
                    self.bondtype = np.append(self.bondtype, mol.bondtype, axis=0)
                else:
                    self.bonds = newbonds
                    self.bondtype = mol.bondtype

            for k in self._atom_and_coord_fields:
                if k == 'serial':
                    continue
                data2 = mol.__dict__[k]
                if mol.__dict__[k] is None or np.size(mol.__dict__[k]) == 0:
                    data2 = self._empty(mol.numAtoms, k)
                self.__dict__[k] = insertappend(index, self.__dict__[k], data2, append)
            self.serial = np.arange(1, self.numAtoms + 1)
            # Reset the box to zeros as you cannot keep box size after inserting atoms
            self.box = np.zeros((3, self.numFrames), dtype=self._dtypes['box'])
            self.boxangles = np.zeros((3, self.numFrames), dtype=self._dtypes['boxangles'])
        except Exception as err:
            self = backup
            raise NameError('Failed to insert/append molecule at position {} with error: "{}"'.format(index, err))

    def remove(self, selection, _logger=True):
        """
        Remove atoms from the Molecule

        Parameters
        ----------
        selection : str
            Atom selection string of the atoms we want to remove.
            See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__

        Returns
        -------
        removed : np.array
            The list of atoms removed

        Example
        -------
        >>> mol=tryp.copy()
        >>> mol.remove('name CA')               # doctest: +ELLIPSIS
        array([   1,    9,   16,   20,   24,   36,   43,   49,   53,   58,...
        """
        sel = self.atomselect(selection, indexes=True)
        self._updateBondsAnglesDihedrals(sel)
        for k in self._atom_and_coord_fields:
            self.__dict__[k] = np.delete(self.__dict__[k], sel, axis=0)
            if k == 'coords':
                self.__dict__[k] = np.atleast_3d(self.__dict__[k])
        if _logger:
            logger.info('Removed {} atoms. {} atoms remaining in the molecule.'.format(len(sel), self.numAtoms))
        return sel

    def get(self, field, sel=None):
        """Retrieve a specific PDB field based on the selection

        Parameters
        ----------
        field : str
            The field we want to get. To see a list of all available fields do `print(Molecule._atom_and_coord_fields)`.
        sel : str
            Atom selection string for which atoms we want to get the field from. Default all.
            See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__

        Returns
        ------
        vals : np.ndarray
            Array of values of `field` for all atoms in the selection.

        Examples
        --------
        >>> mol=tryp.copy()
        >>> mol.get('resname')
        array(['ILE', 'ILE', 'ILE', ..., 'HOH', 'HOH', 'HOH'], dtype=object)
        >>> mol.get('resname', sel='resid 158')
        array(['LEU', 'LEU', 'LEU', 'LEU', 'LEU', 'LEU', 'LEU', 'LEU'], dtype=object)


        """
        if field != 'index' and field not in self._atom_and_coord_fields:
            raise NameError("Invalid field '" + field + "'")
        s = self.atomselect(sel)
        if field == 'coords':
            cc = np.squeeze(self.coords[s, :, self.frame])
            if cc.ndim == 1:
                cc = cc[np.newaxis, :]
            return cc
        elif field == 'index':
            return np.where(s)[0]
        else:
            return self.__dict__[field][s]

    def set(self, field, value, sel=None):
        """Set the values of a Molecule field based on the selection

        Parameters
        ----------
        field : str
            The field we want to set. To see a list of all available fields do `print(Molecule._atom_and_coord_fields)`.
        value : string or integer
            All atoms that match the atom selection will have the field `field` set to this scalar value
            (or 3-vector if setting the coordinates)
        sel : str
            Atom selection string for atom which to set.
            See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__

        Examples
        --------
        >>> mol=tryp.copy()
        >>> mol.set('segid', 'P', sel='protein')
        """
        if field not in self._atom_and_coord_fields:
            raise NameError("Invalid field '" + field + "'")
        s = self.atomselect(sel)
        if field == 'coords':
            self.__dict__[field][s, :, self.frame] = value
        else:
            self.__dict__[field][s] = value

    def align(self, sel, refmol=None, refsel=None, frames=None, matchingframes=False):
        """ Align conformations.

        Align a given set of frames of this molecule to either the current active frame of this molecule (mol.frame)
        or the current frame of a different reference molecule. To align to any frame other than the current active one
        modify the refmol.frame property before calling this method.

        Parameters
        ----------
        sel : str
            Atom selection string for aligning.
            See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__
        refmol : :class:`Molecule`, optional
            Optionally pass a reference Molecule on which to align. If None is given, it will align on the first frame
            of the same Molecule
        refsel : str, optional
            Atom selection for the `refmol` if one is given. Default: same as `sel`.
            See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__
        frames : list or range
            A list of frames which to align. By default it will align all frames of the Molecule
        matchingframes : bool
            If set to True it will align the selected frames of this molecule to the corresponding frames of the refmol.
            This requires both molecules to have the same number of frames.

        Examples
        --------
        >>> mol=tryp.copy()
        >>> mol.align('protein')
        >>> mol.align('name CA', refmol=Molecule('3PTB'))
        """
        from moleculekit.align import _pp_align
        if refmol is None:
            refmol = self
            if matchingframes:
                raise ValueError('You cannot align a molecule\'s frames to themselves. '
                                 'If you want to use the matchingframes option supply a reference molecule.')
        if refsel is None:
            refsel = sel
        if frames is None:
            frames = range(self.numFrames)
        frames = np.array(frames)

        if matchingframes and self.numFrames != refmol.numFrames:
            raise RuntimeError('This molecule and the reference molecule need the same number or frames to use the matchinframes option.')
        
        # if not isinstance(refmol, Molecule):
        # raise NameError('Reference molecule has to be a Molecule object')
        sel = self.atomselect(sel, indexes=True)
        refsel = refmol.atomselect(refsel, indexes=True)
        if sel.size != refsel.size:
            raise NameError('Cannot align molecules. The two selections produced different number of atoms')
        self.coords = _pp_align(self.coords, refmol.coords, np.array(sel, dtype=np.int64),
                                np.array(refsel, dtype=np.int64), frames, refmol.frame, matchingframes)

    def alignBySequence(self, ref, molseg=None, refseg=None, nalignfragment=1, returnAlignments=False, maxalignments=1):
        """ Aligns the Molecule to a reference Molecule by their longest sequence alignment

        Parameters
        ----------
        ref : :class:`Molecule <moleculekit.molecule.Molecule>` object
            The reference Molecule to which we want to align
        molseg : str
            The segment of this Molecule we want to align
        refseg : str
            The segment of `ref` we want to align to
        nalignfragments : int
            The number of fragments used for the alignment.
        returnAlignments : bool
            Return all alignments as a list of Molecules
        maxalignments : int
            The maximum number of alignments we want to produce

        Returns
        -------
        mols : list
            If returnAlignments is True it returns a list of Molecules each containing a different alignment. Otherwise
            it modifies the current Molecule with the best single alignment.
        """
        from moleculekit.tools.sequencestructuralalignment import sequenceStructureAlignment
        aligns = sequenceStructureAlignment(self, ref, molseg, refseg, maxalignments, nalignfragment)
        if returnAlignments:
            return aligns
        else:
            self = aligns[0]

    def append(self, mol, collisions=False, coldist=1.3):
        """ Append a molecule at the end of the current molecule

        Parameters
        ----------
        mol : :class:`Molecule`
            Target Molecule which to append to the end of the current Molecule
        collisions : bool
            If set to True it will remove residues of `mol` which collide with atoms of this Molecule object.
        coldist : float
            Collision distance in Angstrom between atoms of the two molecules. Anything closer will be considered a collision.

        Example
        -------
        >>> mol=tryp.copy()
        >>> mol.filter("not resname BEN")
        >>> lig=tryp.copy()
        >>> lig.filter("resname BEN")
        >>> mol.append(lig)
        """
        self.insert(mol, self.numAtoms, collisions=collisions, coldist=coldist)

    def _getBonds(self, fileBonds=True, guessBonds=True):
        """ Returns an array of all bonds.

        Parameters
        ----------
        fileBonds : bool
            If True will use bonds read from files.
        guessBonds : bool
            If True will use guessed bonds.

        Returns
        -------
        bonds : np.ndarray
            An array of bonds
        """
        bonds = np.empty((0, 2), dtype=np.uint32)
        if fileBonds:
            if len(self.bonds) == 0:  # This is a patch for the other readers not returning correct empty dimensions
                self.bonds = np.empty((0, 2), dtype=np.uint32)
            bonds = np.vstack((bonds, self.bonds))
        if guessBonds:
            bonds = np.vstack((bonds, self._guessBonds()))
        return bonds

    def atomselect(self, sel, indexes=False, strict=False, fileBonds=True, guessBonds=True):
        """ Get a boolean mask or the indexes of a set of selected atoms

        Parameters
        ----------
        sel : str
            Atom selection string. See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__
        indexes : bool
            If True returns the indexes instead of a bitmap
        strict: bool
            If True it will raise an error if no atoms were selected.
        fileBonds : bool
            If True will use bonds read from files.
        guessBonds : bool
            If True will use guessed bonds.

        Return
        ------
        asel : np.ndarray
            Either a boolean mask of selected atoms or their indexes

        Examples
        --------
        >>> mol=tryp.copy()
        >>> mol.atomselect('resname MOL')
        array([False, False, False, ..., False, False, False], dtype=bool)
        """
        from moleculekit.vmdparser import vmdselection
        if sel is None or (isinstance(sel, str) and sel == 'all'):
            s = np.ones(self.numAtoms, dtype=bool)
        elif isinstance(sel, str):
            selc = self.coords[:, :, self.frame].copy()
            s = vmdselection(sel, selc, self.element, self.name, self.resname, self.resid,
                             chain=self.chain,
                             segname=self.segid, insert=self.insertion, altloc=self.altloc, beta=self.beta,
                             occupancy=self.occupancy, bonds=self._getBonds(fileBonds, guessBonds))
            if np.sum(s) == 0 and strict:
                raise NameError('No atoms were selected with atom selection "{}".'.format(sel))
        else:
            s = sel

        s = np.atleast_1d(s)

        if indexes and s.dtype == bool:
            return np.array(np.where(s)[0], dtype=np.int32)
        else:
            return s

    def copy(self):
        """ Create a copy of the Molecule object

        Returns
        -------
        newmol : :class:`Molecule`
            A copy of the object
        """
        return deepcopy(self)

    def filter(self, sel, _logger=True):
        """Removes all atoms not included in the selection

        Parameters
        ----------
        sel: str
            Atom selection string. See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__

        Examples
        --------
        >>> mol=tryp.copy()
        >>> mol.filter('protein')
        """
        s = self.atomselect(sel)
        if np.all(s):  # If all are selected do nothing
            return np.array([], dtype=np.int32)

        if not isinstance(s, np.ndarray) or s.dtype != bool:
            raise NameError('Filter can only work with string inputs or boolean arrays')
        return self.remove(np.invert(s), _logger=_logger)

    def _updateBondsAnglesDihedrals(self, idx):
        """ Renumbers bonds after removing atoms and removes non-existent bonds

        Needs to be called before removing atoms!
        """
        if len(idx) == 0:
            return
        if len(self.bonds) == 0 and len(self.dihedrals) == 0 and len(self.impropers) == 0 and len(self.angles) == 0:
            return
        map = np.ones(self.numAtoms, dtype=int)
        map[idx] = -1
        map[map == 1] = np.arange(self.numAtoms - len(idx))
        for field in ('bonds', 'angles', 'dihedrals', 'impropers'):
            if len(self.__dict__[field]) == 0:
                continue
            # Have to store in temp because they can be uint which can't accept -1 values
            tempdata = np.array(self.__dict__[field], dtype=np.int32)
            tempdata[:] = map[tempdata[:]]
            stays = np.invert(np.any(tempdata == -1, axis=1))
            # Delete bonds/angles/dihedrals between non-existent atoms
            self.__dict__[field] = tempdata[stays, ...]
            if field == 'bonds' and len(self.bondtype):
                self.bondtype = self.bondtype[stays]

    def deleteBonds(self, sel, inter=True):
        """ Deletes all bonds that contain atoms in sel or between atoms in sel.

        Parameters
        ----------
        sel : str
            Atom selection string of atoms whose bonds will be deleted.
            See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__
        inter : bool
            When True it will delete also bonds between atoms in sel with bonds to atoms outside of sel.
            When False it will only delete bonds between atoms in sel.
        """
        sel = self.atomselect(sel, indexes=True)
        if len(sel) == 0:  # If none are selected do nothing
            return
        if inter:
            todel = np.in1d(self.bonds[:, 0], sel) | np.in1d(self.bonds[:, 1], sel)
        else:
            todel = np.in1d(self.bonds[:, 0], sel) & np.in1d(self.bonds[:, 1], sel)
        idx = np.where(todel)[0]
        self.bonds = np.delete(self.bonds, idx, axis=0)
        self.bondtype = np.delete(self.bondtype, idx)

    def _guessBonds(self):
        """ Tries to guess the bonds in the Molecule

        Can fail badly when non-bonded atoms are very close together. Use with extreme caution.
        """
        from moleculekit.vmdparser import guessbonds
        framecoords = self.coords[:, :, self.frame].copy()
        return guessbonds(framecoords, self.element, self.name, self.resname, self.resid, self.chain, self.segid,
                                self.insertion, self.altloc)

    def moveBy(self, vector, sel=None):
        """ Move a selection of atoms by a given vector

        Parameters
        ----------
        vector: list
            3D coordinates to add to the Molecule coordinates
        sel: str
            Atom selection string of atoms which we want to move.
            See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__

        Examples
        --------
        >>> mol=tryp.copy()
        >>> mol.moveBy([3, 45 , -8])
        """
        vector = np.array(vector)
        if np.size(vector) != 3:
            raise NameError('Move vector must be a 1x3 dimensional vector.')
        vector.shape = [1, 3]  # Forces it to be row vector

        s = self.atomselect(sel)
        self.coords[s, :, self.frame] += vector

    def rotateBy(self, M, center=(0, 0, 0), sel='all'):
        """ Rotate a selection of atoms by a given rotation matrix around a center

        Parameters
        ----------
        M : np.ndarray
            The rotation matrix
        center : list
            The rotation center
        sel : str
            Atom selection string for atoms to rotate.
            See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__

        Examples
        --------
        >>> mol = tryp.copy()
        >>> mol.rotateBy(rotationMatrix([0, 1, 0], 1.57))
        """
        if abs(np.linalg.det(M)-1) > 1e-5:
            logger.warning("Suspicious non-unitary determinant: {:f}".format(np.linalg.det(M)))
        coords = self.get('coords', sel=sel)
        newcoords = coords - center
        newcoords = np.dot(newcoords, np.transpose(M)) + center
        self.set('coords', newcoords, sel=sel)

    def getDihedral(self, atom_quad):
        """ Get the value of a dihedral angle.

        Parameters
        ----------
        atom_quad : list
            Four atom indexes corresponding to the atoms defining the dihedral

        Returns
        -------
        angle: float
            The angle in radians

        Examples
        --------
        >>> mol.getDihedral([0, 5, 8, 12])
        """
        from moleculekit.dihedral import dihedralAngle
        return dihedralAngle(self.coords[atom_quad, :, self.frame])

    def setDihedral(self, atom_quad, radians, bonds=None):
        """ Sets the angle of a dihedral.
        
        Parameters
        ----------
        atom_quad : list
            Four atom indexes corresponding to the atoms defining the dihedral
        radians : float
            The angle in radians to which we want to set the dihedral
        bonds : np.ndarray
            An array containing all bonds of the molecule. This is needed if multiple modifications are done as the
            bond guessing can get messed up if atoms come very close after the rotation.

        Examples
        --------
        >>> mol.setDihedral([0, 5, 8, 12], 0.16)
        >>> # If we perform multiple modifications, calculate bonds first and pass them as argument to be safe
        >>> bonds = mol._getBonds()
        >>> mol.setDihedral([0, 5, 8, 12], 0.16, bonds=bonds)
        >>> mol.setDihedral([18, 20, 24, 30], -1.8, bonds=bonds)
        """
        import scipy.sparse.csgraph as sp
        from moleculekit.util import rotationMatrix
        from moleculekit.dihedral import dihedralAngle
        if bonds is None:
            bonds = self._getBonds()

        # Now we have to make the lists of atoms that are on either side of the dihedral bond
        natoms = self.numAtoms
        conn = np.zeros((natoms, natoms), dtype=np.bool)
        for b in bonds:
            conn[b[0], b[1]] = True
            conn[b[1], b[0]] = True

        # disconnect the structure across the dihedral bond
        conn[[atom_quad[1], atom_quad[2]]] = 0
        conn[[atom_quad[2], atom_quad[1]]] = 0
        left = np.unique(sp.breadth_first_tree(conn, atom_quad[1], directed=False).indices.flatten())
        right = np.unique(sp.breadth_first_tree(conn, atom_quad[2], directed=False).indices.flatten())

        if (atom_quad[2] in left) or (atom_quad[1] in right):
            raise RuntimeError('Loop detected in molecule. Cannot change dihedral')

        quad_coords = self.coords[atom_quad, :, self.frame]
        rotax = quad_coords[2] - quad_coords[1]
        rotax /= np.linalg.norm(rotax)
        rads = dihedralAngle(quad_coords)
        M = rotationMatrix(rotax, radians-rads)
        self.rotateBy(M, center=self.coords[atom_quad[1], :, self.frame], sel=right)

    def center(self, loc=(0, 0, 0), sel='all'):
        """ Moves the geometric center of the Molecule to a given location

        Parameters
        ----------
        loc : list, optional
            The location to which to move the geometric center
        sel : str
            Atom selection string of the atoms whose geometric center we want to center on the `loc` position.
            See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__

        Examples
        --------
        >>> mol=tryp.copy()
        >>> mol.center()
        >>> mol.center([10, 10, 10], 'name CA')
        """
        sel = self.atomselect(sel)
        com = np.mean(self.coords[sel, :, self.frame], 0)
        self.moveBy(-com)
        self.moveBy(loc)

    def read(self, filename, type=None, skip=None, frames=None, append=False, overwrite='all', keepaltloc='A', guess=None, guessNE=None, _logger=True, **kwargs):
        """ Read topology, coordinates and trajectory files in multiple formats.

        Detects from the extension the file type and loads it into Molecule

        Parameters
        ----------
        filename : str
            Name of the file we want to read
        type : str, optional
            File type of the file. If None, it's automatically determined by the extension
        skip : int, optional
            If the file is a trajectory, skip every `skip` frames
        frames : list, optional
            If the file is a trajectory, read only the given frames
        append : bool, optional
            If the file is a trajectory or coor file, append the coordinates to the previous coordinates. Note append is slow.
        overwrite : str, list of str
            A list of the existing fields in Molecule that we wish to overwrite when reading this file. Set to None if
            you don't want to overwrite any existing fields.
        keepaltloc : str
            Set to any string to only keep that specific altloc. Set to 'all' if you want to keep all alternative atom positions.
        guess : list of str
            Properties of the molecule to guess. Can be any combination of ('bonds', 'angles', 'dihedrals')
        guessNE : list of str
            Properties of the molecule to guess if it's Non-Existent. Can be any combination of ('bonds', 'angles', 'dihedrals')
        """
        try:
            from htmd.simlist import Sim, Frame
        except ImportError:
            Sim = Frame = ()  # Empty tuple to disable isinstance checks
        from moleculekit.readers import _MDTRAJ_TRAJECTORY_EXTS, _ALL_READERS, FormatError, _TRAJECTORY_READERS

        # If a single filename is specified, turn it into an array so we can iterate
        from moleculekit.util import ensurelist
        filename = ensurelist(filename)

        if frames is not None:
            frames = ensurelist(frames)
            if len(filename) != len(frames):
                raise NameError('Number of trajectories ({}) does not match number of frames ({}) given as arguments'.format(len(filename), len(frames)))
        else:
            frames = [None] * len(filename)

        for f in filename:
            if not isinstance(f, Sim) and not isinstance(f, Frame) and len(f) != 4 and not os.path.exists(f):
                raise FileNotFoundError('File {} was not found.'.format(f))

        if len(filename) == 1 and isinstance(filename[0], Sim):
            self.read(filename[0].molfile) # TODO: Should pass all parameters here!!!
            self.read(filename[0].trajectory)
            return
        if len(filename) == 1 and isinstance(filename[0], Frame):
            self.read(filename[0].sim.molfile)
            self.read(filename[0].sim.trajectory[filename[0].piece])
            self.dropFrames(keep=filename[0].frame)
            return

        newmols = []
        for fname, frame in zip(filename, frames):
            fname = self._unzip(fname)
            ext = self._getExt(fname, type)

            # To use MDTraj we need to write out a PDB file to use it to read the trajs
            tmppdb = None
            if ext in _MDTRAJ_TRAJECTORY_EXTS:
                tmppdb = tempname(suffix='.pdb')
                self.write(tmppdb)

            if ext not in _ALL_READERS:
                raise ValueError('Unknown file type with extension "{}".'.format(ext))
            readers = _ALL_READERS[ext]
            mol = None
            for rr in readers:
                try:
                    mol = rr(fname, frame=frame, topoloc=tmppdb, **kwargs)
                except FormatError:
                    continue
                else:
                    break

            if tmppdb is not None:
                os.remove(tmppdb)

            if mol is None:
                raise RuntimeError('No molecule read from file {} with any of the readers {}'.format(fname, readers))

            if isinstance(mol, list):
                raise AssertionError('Reader {} should not return multiple molecules. Report this error on github.')

            if self.numAtoms != 0 and mol.numAtoms != self.numAtoms:
                raise ValueError('Number of atoms in file ({}) mismatch with number of atoms in the molecule '
                                 '({})'.format(mol.numAtoms, self.numAtoms))

            # TODO: Needs redesign to remove hack
            if frame is not None and ext != 'xtc':
                mol.dropFrames(keep=frame)

            newmols.append(mol)

        self._mergeTopologies(newmols, overwrite=overwrite, _logger=_logger)
        self._mergeTrajectories(newmols, append=append, skip=skip)

        self._dropAltLoc(keepaltloc=keepaltloc, _logger=_logger)

        if guess is not None or guessNE is not None:
            if guess is not None:
                guess = ensurelist(guess)
            if guessNE is not None:
                guessNE = ensurelist(guessNE)
            if 'bonds' in guess or ('bonds' in guessNE and len(self.bonds) == 0):
                self.bonds = self._guessBonds()
                self.bondtype = np.array(['un'] * self.bonds.shape[0], dtype=Molecule._dtypes['bondtype'])
            if 'dihedrals' in guess or 'angles' in guess:
                from moleculekit.util import guessAnglesAndDihedrals
                angles, dihedrals = guessAnglesAndDihedrals(self.bonds)
                if 'angles' in guess or ('angles' in guessNE and len(self.angles) == 0):
                    self.angles = angles
                if 'dihedrals' in guess or ('dihedrals' in guessNE and len(self.dihedrals) == 0):
                    self.dihedrals = dihedrals

    def _getExt(self, fname, type):
        from moleculekit.readers import _ALL_READERS
        if type is not None and type.lower() in _ALL_READERS:
            return type
        if not os.path.isfile(fname) and len(fname) == 4:
            return 'pdb'
        return os.path.splitext(fname)[1][1:]

    def _unzip(self, fname):
        if fname.endswith('.gz'):
            import gzip
            from moleculekit.util import tempname
            with gzip.open(fname, 'r') as f:
                fname = tempname(suffix='.{}'.format(fname.split('.')[-2]))
                with open(fname, 'w') as fo:
                    fo.write(f.read().decode('utf-8', errors='ignore'))
        return fname

    def _dropAltLoc(self, keepaltloc='A', _logger=True):
        # Dropping atom alternative positions
        otheraltlocs = [x for x in np.unique(self.altloc) if len(x) and x != keepaltloc]
        if len(otheraltlocs) >= 1 and not keepaltloc == 'all' and _logger:
            logger.warning('Alternative atom locations detected. Only altloc {} was kept. If you prefer to keep all '
                           'use the keepaltloc="all" option when reading the file.'.format(keepaltloc))
            for a in otheraltlocs:
                self.remove(self.altloc == a, _logger=_logger)

    def _mergeTopologies(self, newmols, overwrite='all', _logger=True):
        if isinstance(overwrite, str):
            overwrite = (overwrite, )

        for mol in newmols:
            if mol._numAtomsTopo == 0:
                continue

            if self._numAtomsTopo == 0:
                self._emptyTopo(mol.numAtoms)

            if (len(self.name) == mol._numAtomsTopo) and np.any(mol.name != '') and np.any(self.name != '') and not np.array_equal(self.name, mol.name):
                if len(np.setdiff1d(self.name, mol.name)) == 0:
                    logger.warning('Same atoms read in different order from topology file {}. Will reorder atom information to match existing ones in Molecule.'.format(mol.fileloc))
                    if len(np.unique(self.name)) != len(self.name):
                        msg = 'Cannot reorder atoms due to non-unique atom names in molecule.'
                        if overwrite == 'all':
                            logger.warning(msg + ' Will overwrite all fields.')
                        else:
                            raise RuntimeError(msg)
                    else:
                        order = np.array([np.where(mol.name == nn)[0][0] for nn in self.name])
                        mol.reorderAtoms(order)
                else:
                    raise TopologyInconsistencyError('Same number of atoms but different atom names read from topology file {}'.format(mol.fileloc))

            for field in mol._topo_fields:
                if field == 'crystalinfo':
                    continue

                newfielddata = mol.__dict__[field]

                # Continue if all values in the new mol are empty or zero
                if newfielddata is None or len(newfielddata) == 0 or np.all([x is None for x in newfielddata]):
                    continue
                if self._dtypes[field] == object and np.all(newfielddata == ''):
                    continue
                if self._dtypes[field] != object and np.all(newfielddata == 0):
                    continue

                if field in Molecule._atom_fields and np.shape(self.__dict__[field]) != np.shape(newfielddata):
                    raise TopologyInconsistencyError(
                        'Different number of atoms read from topology file {} for field {}'.format(mol.fileloc, field))

                if overwrite is not None and ((overwrite[0] == 'all') or (field in overwrite)):
                    self.__dict__[field] = newfielddata
                else:
                    if not np.array_equal(self.__dict__[field], newfielddata):
                        raise TopologyInconsistencyError(
                            'Different atom information read from topology file {} for field {}'.format(mol.fileloc,
                                                                                                        field))

            if len(self.bonds) != 0 and len(self.bondtype) == 0:
                self.bondtype = np.empty(self.bonds.shape[0], dtype=Molecule._dtypes['bondtype'])
                self.bondtype[:] = 'un'

            self.element = self._guessMissingElements()
            self.crystalinfo = mol.crystalinfo
            self.topoloc = mol.topoloc
            self.fileloc = mol.fileloc
            self.viewname = mol.viewname

    def write(self, filename, sel=None, type=None, **kwargs):
        """ Writes the topology and coordinates of the Molecule in any of the supported formats.

        Parameters
        ----------
        filename : str
            The filename of the file we want to write to disk
        sel : str, optional
            Atom selection string of the atoms we want to write. If None, it will write all atoms.
            See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__
        type : str, optional
            The filetype we want to write. By default, detected from the file extension
        """
        from moleculekit.writers import _WRITERS
        if type:
            type = type.lower()
        ext = os.path.splitext(filename)[1][1:]
        if ext == 'gz':
            pieces = filename.split('.')
            ext = '{}.{}'.format(pieces[-2], pieces[-1])

        src = self
        if not (sel is None or (isinstance(sel, str) and sel == 'all')):
            src = self.copy()
            src.filter(sel, _logger=False)

        if type in _WRITERS:
            ext = type
        if ext in _WRITERS:
            _WRITERS[ext](src, filename, **kwargs)
        else:
            raise IOError('Molecule cannot write files with "{}" extension yet. If you need such support please notify '
                        'us on the github moleculekit issue tracker.'.format(ext))

    def reorderAtoms(self, order):
        """ Reorder atoms in Molecule

        Changes the order of atoms in the Molecule to the defined order.

        Parameters
        ----------
        order : list
            A list containing the new order of atoms

        Examples
        --------
        >>> mol = Molecule()
        >>> mol.empty(4)
        >>> mol.name[:] = ['N', 'C', 'H', 'S']
        >>> neworder = [1, 3, 2, 0]
        >>> mol.reorderAtoms(neworder)
        >>> print(mol.name)
        array(['C', 'S', 'H', 'N'], dtype=object)
        """
        order = np.array(order)
        for field in Molecule._atom_and_coord_fields:
            if len(self.__dict__[field]) == 0:
                continue
            self.__dict__[field] = self.__dict__[field][order]

        # Change indexes to match order
        inverseorder = np.array([np.where(order == i)[0][0] for i in np.arange(len(order))])
        for field in Molecule._connectivity_fields:
            if len(self.__dict__[field]) == 0:
                continue
            if field == 'bondtype':
                continue
            self.__dict__[field] = inverseorder[self.__dict__[field]]

    def _mergeTrajectories(self, newmols, skip=None, append=False):
        from collections import defaultdict
        trajinfo = defaultdict(list)
        if append and self._numAtomsTraj != 0:
            for field in Molecule._traj_fields:
                trajinfo[field].append(self.__dict__[field])

        for mol in newmols:
            if mol._numAtomsTraj == 0:
                continue

            for field in Molecule._traj_fields:
                if field == 'fileloc':  # TODO: Make a PR where fileloc becomes (2, nframes) numpy array so we don't handle it separately
                    trajinfo[field] += mol.__dict__[field]
                else:
                    trajinfo[field].append(mol.__dict__[field])

        if len(trajinfo):
            for field in Molecule._traj_fields:
                if field == 'fileloc':
                    self.__dict__[field] = trajinfo[field]
                else:
                    self.__dict__[field] = np.concatenate(trajinfo[field], axis=-1)

        if self._numAtomsTopo != 0 and self._numAtomsTraj == 0:
            self._emptyTraj(self._numAtomsTopo)
            return

        if skip is not None:
            self.coords = np.array(self.coords[:, :, ::skip])  # np.array is required to make copy and thus free memory!
            if self.box is not None:
                self.box = np.array(self.box[:, ::skip])
            if self.boxangles is not None:
                self.boxangles = self.boxangles[:, ::skip]
            if self.step is not None:
                self.step = self.step[::skip]
            if self.time is not None:
                self.time = self.time[::skip]
            self.fileloc = self.fileloc[::skip]

        self.coords = np.atleast_3d(self.coords)

    def mutateResidue(self, sel, newres):
        """ Mutates a residue by deleting its sidechain and renaming it

        Parameters
        ----------
        sel : str
            Atom selection string for the residue we want to mutate. The selection needs to include all atoms of the
            residue. See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__
        newres : str
            The name of the new residue

        Examples
        --------
        >>> mol=tryp.copy()
        >>> mol.mutateResidue('resid 158', 'ARG')
        """
        s = self.atomselect(sel, strict=True)
        # Changed the selection from "and sidechain" to "not backbone" to remove atoms like phosphates which are bonded
        # but not part of the sidechain. Changed again the selection to "name C CA N O" because "backbone" works for
        # both protein and nucleic acid backbones and it confuses phosphates of modified residues for nucleic backbones.
        remidx = self.atomselect(sel + ' and not name C CA N O', indexes=True)
        self.remove(remidx, _logger=False)
        s = np.delete(s, remidx)
        self.set('resname', newres, sel=s)

    def wrap(self, wrapsel=None, fileBonds=True, guessBonds=True):
        """ Wraps the coordinates of the molecule into the simulation box

        Parameters
        ----------
        wrapsel : str
            Atom selection string of atoms on which to center the wrapping box.
            See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__

        Examples
        --------
        >>> mol=tryp.copy()
        >>> mol.wrap()
        >>> mol.wrap('protein')
        """
        from moleculekit.wrap import wrap
        # TODO: selection is not used. WHY?
        if wrapsel is not None:
            centersel = self.atomselect(wrapsel, indexes=True)
        else:
            centersel = None
        self.coords = wrap(self.coords, self._getBonds(fileBonds, guessBonds), self.box, centersel=centersel)

    def _emptyTopo(self, numAtoms):
        for field in Molecule._atom_fields:
            self.__dict__[field] = self._empty(numAtoms, field)

    def _emptyTraj(self, numAtoms):
        self.coords = self._empty(numAtoms, 'coords')
        self.box = np.zeros(self._dims['box'], dtype=np.float32)


    def empty(self, numAtoms):
        """ Creates an empty molecule of `numAtoms` atoms.

        Parameters
        ----------
        numAtoms : int
            Number of atoms to create in the molecule.

        Example
        -------
        >>> newmol = Molecule().empty(100)
        """
        self._emptyTopo(numAtoms)
        self._emptyTraj(numAtoms)
        return self

    def sequence(self, oneletter=True, noseg=False):
        """ Return the aminoacid sequence of the Molecule.

        Parameters
        ----------
        oneletter : bool
            Whether to return one-letter or three-letter AA codes. There should be only one atom per residue.
        noseg : bool
            Ignore segments and return the whole sequence as single string.

        Returns
        -------
        sequence : str
            The primary sequence as a dictionary segid - string (if oneletter is True) or segid - list of
            strings (otherwise).

        Examples
        --------
        >>> mol=tryp.copy()
        >>> mol.sequence()
        {'0': 'IVGGYTCGANTVPYQVSLNSGYHFCGGSLINSQWVVSAAHCYKSGIQVRLGEDNINVVEGNEQFISASKSIVHPSYNSNTLNNDIMLIKLKSAASLNSRVASISLPTSCASAGTQCLISGWGNTKSSGTSYPDVLKCLKAPILSDSSCKSAYPGQITSNMFCAGYLEGGKDSCQGDSGGPVVCSGKLQGIVSWGSGCAQKNKPGVYTKVCNYVSWIKQTIASN'}
        >>> sh2 = Molecule("1LKK")
        >>> pYseq = sh2.sequence(oneletter=False)
        >>> pYseq['1']
        ['PTR', 'GLU', 'GLU', 'ILE']
        >>> pYseq = sh2.sequence(oneletter=True)
        >>> pYseq['1']
        'XEEI'

        """
        from moleculekit.util import sequenceID
        prot = self.atomselect('protein')

        increm = sequenceID((self.resid, self.insertion, self.chain))
        segs = np.unique(self.segid[prot])
        segSequences = {}
        if noseg:
            segs = ['protein']

        # Iterate over segments
        for seg in segs:
            segSequences[seg] = []
            if seg != 'protein':
                segatoms = prot & (self.segid == seg)
            else:
                segatoms = prot
            resnames = self.resname[segatoms]
            incremseg = increm[segatoms]
            for i in np.unique(incremseg):  # Iterate over residues
                resname = np.unique(resnames[incremseg == i])
                if len(resname) != 1:
                    raise AssertionError('Unexpected non-uniqueness of chain, resid, insertion in the sequence.')
                resname = resname[0]
                if oneletter:
                    if resname in _residueNameTable:
                        rescode = _residueNameTable[resname]
                    elif resname in _modResidueNameTable:
                        rescode = _modResidueNameTable[resname]
                        logger.warning("Modified residue {} was detected in the protein and mapped to one-letter "
                                       "code {}".format(resname, rescode))
                    else:
                        rescode = 'X'
                        logger.warning("Cannot provide one-letter code for non-standard residue {}".format(resname))
                else:
                    rescode = resname
                segSequences[seg].append(rescode)

        # Join single letters into strings
        if oneletter:
            segSequences = {k: "".join(segSequences[k]) for k in segSequences}

        return segSequences

    def dropFrames(self, keep='all', drop=None):
        """ Removes trajectory frames from the Molecule

        Parameters
        ----------
        keep : int or list of ints
            Index of frame, or list of frame indexes which we want to keep (and drop all others).
        drop : int or list of ints
            Index of frame, or list of frame indexes which we want to drop (and keep all others).
        Examples
        --------
        >>> mol = Molecule('1sb0')
        >>> mol.dropFrames(keep=[1,2])
        >>> mol.numFrames == 2
        >>> mol.dropFrames(drop=[0])
        >>> mol.numFrames == 1
        """
        from moleculekit.util import ensurelist
        if not (isinstance(keep, str) and keep == 'all') and drop is not None:
            raise RuntimeError('Cannot both drop and keep trajectories. Please use only one of the two arguments.')
        numframes = self.numFrames
        if drop is not None:
            keep = np.setdiff1d(np.arange(numframes), drop)
        keep = ensurelist(keep)
        if not (isinstance(keep, str) and keep == 'all'):
            self.coords = np.atleast_3d(self.coords[:, :, keep]).copy()  # Copy array. Slices are dangerous with C
            if self.box.shape[1] == numframes:
                self.box = np.atleast_2d(self.box[:, keep]).copy()
                if self.box.shape[0] == 1:
                    self.box = self.box.T
            if self.boxangles.shape[1] == numframes:
                self.boxangles = np.array(np.atleast_2d(self.boxangles[:, keep]))
                if self.boxangles.shape[0] == 1:
                    self.boxangles = self.boxangles.T
            if len(self.step) == numframes:
                self.step = self.step[keep]
            if len(self.time) == numframes:
                self.time = self.time[keep]
            if len(self.fileloc) == numframes:
                self.fileloc = [self.fileloc[i] for i in keep]
        self.frame = 0  # Reset to 0 since the frames changed indexes

    def _guessBabelElements(self):
        babel_elements = ['Cr', 'Pt', 'Mn', 'Np', 'Be', 'Co', 'Rn', 'C', 'Ag', 'Xe', 'D', 'Th', 'Sb', 'Al', 'Ir', 'In', 'Te', 'Tl', 'K', 'Tb', 'Br', 'Eu', 'Ne', 'Rb', 'Ar', 'Sm', 'Xx', 'Fe', 'Lr', 'S', 'H', 'He', 'At', 'Li', 'Cs', 'Rh', 'Nb', 'Pr', 'Fm', 'Cu', 'Ru', 'Ga', 'Er', 'Hg', 'Nd', 'Ba', 'Ta', 'Pu', 'O', 'Pb', 'Yb', 'Bk', 'Pd', 'F', 'Gd', 'Y', 'Ac', 'Au', 'Hf', 'Ra', 'V', 'I', 'Ge', 'Re', 'Fr', 'Cm', 'Kr', 'Sr', 'Sn', 'Pm', 'Ca', 'No', 'Si', 'Es', 'U', 'Am', 'Sc', 'Md', 'As', 'Na', 'N', 'Dy', 'Os', 'Po', 'Se', 'Lu', 'Mo', 'Zn', 'Cd', 'Mg', 'Tm', 'Cl', 'P', 'B', 'W', 'Tc', 'Cf', 'Bi', 'Ni', 'Ti', 'Pa', 'La', 'Ce', 'Zr', 'Ho']
        guess_babel_elements = ['D', 'M', 'V', 'A', 'X', 'R', 'F', 'Z', 'T', 'E', 'G', 'L']
        from moleculekit.writers import _deduce_PDB_atom_name, _getPDBElement
        elements = []
        for i, elem in enumerate(self.element):
            if len(elem) != 0 and isinstance(elem, str) and elem in babel_elements:
                elements.append(elem)
            else:
                # Get the 4 character PDB atom name
                name = _deduce_PDB_atom_name(self.name[i], self.resname[i])
                # Deduce from the 4 character atom name the element
                elem = _getPDBElement(name, elem)
                if elem in babel_elements:
                    elements.append(elem)
                else:
                    # Really risky business here
                    celem = name[0].upper()
                    if len(name) > 1:
                        celem += name[1].lower()
                    if celem in babel_elements:
                        elements.append(celem)
                    else:
                        elements.append('Xx')
        return elements

    def _guessMissingElements(self):
        from moleculekit.writers import _deduce_PDB_atom_name, _getPDBElement
        elements = self.element.copy()
        emptyidx = np.where(elements == '')[0]
        for i in emptyidx:
            # Get the 4 character PDB atom name
            name = _deduce_PDB_atom_name(self.name[i], self.resname[i])
            # Deduce from the 4 character atom name the element
            elem = _getPDBElement(name, '', lowersecond=False)
            elements[i] = elem
        return elements

    def appendFrames(self, mol):
        """ Appends the frames of another Molecule object to this object.

        Parameters
        ----------
        mol : :class:`Molecule`
            A Molecule object.
        """
        fstep = self.fstep
        if (fstep !=0 and mol.fstep !=0) and (fstep != mol.fstep):
            raise RuntimeError('Cannot concatenate Molecules with different fsteps')
        self.coords = np.concatenate((self.coords, mol.coords), axis=2)
        self.box = np.concatenate((self.box, mol.box), axis=1)
        self.boxangles = np.concatenate((self.boxangles, mol.boxangles), axis=1)
        self.fileloc += mol.fileloc
        self.step = np.concatenate((self.step, mol.step))
        self.time = np.concatenate((self.time, mol.time))

    def renumberResidues(self, returnMapping=False):
        """ Renumbers protein residues incrementally.

        It checks for changes in either of the resid, insertion, chain or segid fields and in case of a change it
        creates a new residue number.

        Parameters
        ----------
        returnMapping : bool
            If set to True, the method will also return the mapping between the old and new residues

        Examples
        --------
        >>> mapping = mol.renumberResidues(returnMapping=True)
        """
        from moleculekit.util import sequenceID
        if returnMapping:
            resid = self.resid.copy()
            insertion = self.insertion.copy()
            resname = self.resname.copy()
            chain = self.chain.copy()
            segid = self.segid.copy()

        self.resid[:] = sequenceID((self.resid, self.insertion, self.chain, self.segid))
        self.insertion[:] = ''

        if returnMapping:
            import pandas as pd
            from collections import OrderedDict
            firstidx = np.where(np.diff([-1] + self.resid.tolist()) == 1)[0]
            od = OrderedDict({'new_resid': self.resid[firstidx],
                              'resid': resid[firstidx],
                              'insertion': insertion[firstidx],
                              'resname': resname[firstidx],
                              'chain': chain[firstidx],
                              'segid': segid[firstidx]})
            mapping = pd.DataFrame(od)
            return mapping

    @property
    def numFrames(self):
        """ Number of coordinate frames in the molecule
        """
        return np.size(np.atleast_3d(self.coords), 2)

    @property
    def _numAtomsTopo(self):
        return len(self.record)

    @property
    def _numAtomsTraj(self):
        return self.coords.shape[0]

    @property
    def numAtoms(self):
        """ Number of atoms in the molecule
        """
        natoms = self._numAtomsTopo
        if natoms == 0:
            natoms = self._numAtomsTraj
        return natoms

    @property
    def x(self):
        """Get the x coordinates at the current frame"""
        return self.coords[:, 0, self.frame]

    @property
    def y(self):
        """Get the y coordinates at the current frame"""
        return self.coords[:, 1, self.frame]

    @property
    def z(self):
        """Get the z coordinates at the current frame"""
        return self.coords[:, 2, self.frame]

    def __repr__(self):
        return '<{}.{} object at {}>\n'.format(self.__class__.__module__, self.__class__.__name__, hex(id(self))) \
               + self.__str__()

    def __str__(self):
        def formatstr(name, field):
            if isinstance(field, np.ndarray) or isinstance(field, list):
                rep = '{} shape: {}'.format(name, np.shape(field))
            elif field == 'reps':
                rep = '{}: {}'.format(name, len(self.reps.replist))
            else:
                rep = '{}: {}'.format(name, field)
            return rep

        rep = 'Molecule with ' + str(self.numAtoms) + ' atoms and ' + str(self.numFrames) + ' frames'
        for p in sorted(self._atom_and_coord_fields):
            rep += '\n'
            rep += 'Atom field - ' + formatstr(p, self.__dict__[p])
        for j in sorted(self.__dict__.keys() - list(Molecule._atom_and_coord_fields)):
            if j[0] == '_':
                continue
            rep += '\n'
            rep += formatstr(j, self.__dict__[j])

        return rep

    def view(self, sel=None, style=None, color=None, guessBonds=True, viewer=None, hold=False, name=None,
             viewerhandle=None, gui=False):
        """ Visualizes the molecule in a molecular viewer

        Parameters
        ----------
        sel : str
            Atom selection string for the representation.
            See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__
        style : str
            Representation style. See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node55.html>`__.
        color : str or int
            Coloring mode (str) or ColorID (int).
            See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node85.html>`__.
        guessBonds : bool
            Allow VMD to guess bonds for the molecule
        viewer : str ('vmd', 'webgl')
            Choose viewer backend. Default is taken from either moleculekit.config or if it doesn't exist from moleculekit.config
        hold : bool
            If set to True, it will not visualize the molecule but instead collect representations until set back to False.
        name : str, optional
            A name to give to the molecule in VMD
        viewerhandle : :class:`VMD <moleculekit.vmdviewer.VMD>` object, optional
            A specific viewer in which to visualize the molecule. If None it will use the current default viewer.
        """
        from moleculekit.util import tempname

        if self.numFrames == 0:
            raise RuntimeError('No frames in this molecule to visualize.')

        if sel is not None or style is not None or color is not None:
            self._tempreps.add(sel=sel, style=style, color=color)

        if hold:
            return

        bonds = None
        if guessBonds:
            bonds = self._getBonds()

        # Write out PSF and XTC files
        pdb = None
        psf = tempname(suffix=".psf")
        self.write(psf, explicitbonds=bonds)

        xtc = tempname(suffix=".xtc")
        self.write(xtc)

        # Call the specified backend
        retval = None
        if viewer is None:
            try:
                from htmd.config import _config
                viewer = _config['viewer']
            except:
                from moleculekit.config import _config
                viewer = _config['viewer']
        if viewer.lower() == 'vmd':
            pdb = tempname(suffix=".pdb")
            self.write(pdb, writebonds=False)
            self._viewVMD(psf, pdb, xtc, viewerhandle, name, guessBonds)
        elif viewer.lower() == 'ngl' or viewer.lower() == 'webgl':
            retval = self._viewNGL(gui=gui)
        else:
            os.remove(xtc)
            os.remove(psf)
            if pdb is not None:
                os.remove(pdb)
            raise ValueError('Unknown viewer.')

        # Remove temporary files
        os.remove(xtc)
        os.remove(psf)
        if pdb is not None:
            os.remove(pdb)
        if retval is not None:
            return retval

    def _viewVMD(self, psf, pdb, xtc, vhandle, name, guessbonds):
        from moleculekit.vmdviewer import getCurrentViewer
        if name is None:
            name = self.viewname
        if vhandle is None:
            vhandle = getCurrentViewer()

        if guessbonds:
            vhandle.send("mol new " + pdb)
            vhandle.send("mol addfile " + psf)

        else:
            vhandle.send("mol new " + pdb + " autobonds off")
            vhandle.send("mol addfile " + psf + " autobonds off")
        vhandle.send('animate delete all')
        vhandle.send('mol addfile ' + xtc + ' type xtc waitfor all')

        if name is not None:
            vhandle.send('mol rename top "' + name + '"')
        else:
            vhandle.send('mol rename top "Mol [molinfo top]: pdb+psf+xtc"')

        self._tempreps.append(self.reps)
        self._tempreps._repsVMD(vhandle)
        self._tempreps.remove()

    def _viewNGL(self, gui=False):
        try:
            import nglview
        except ImportError:
            raise ImportError('Optional package nglview not found. Please install it using `conda install nglview -c acellera`.')
        from nglview import HTMDTrajectory
        traj = HTMDTrajectory(self)
        w = nglview.NGLWidget(traj, gui=gui)

        self._tempreps.append(self.reps)
        self._tempreps._repsNGL(w)
        self._tempreps.remove()
        return w


class UniqueAtomID:
    _fields = ('name', 'altloc', 'resname', 'chain', 'resid', 'insertion', 'segid')

    def __init__(self, **kwargs):
        """ Unique atom identifier

        Parameters
        ----------
        kwargs

        Examples
        --------
        >>> mol = Molecule('3ptb')
        >>> uqid = UniqueAtomID.fromMolecule(mol, 'resid 20 and name CA')
        >>> uqid.selectAtom(mol)
        24
        >>> _ = mol.remove('resid 19')
        >>> uqid.selectAtom(mol)
        20
        """
        for key in kwargs:
            if key in UniqueAtomID._fields:
                setattr(self, key, kwargs[key])
            else:
                raise KeyError('Invalid key {}. The constructor only supports the '
                               'following fields: {}'.format(key, UniqueAtomID._fields))

    @staticmethod
    def fromMolecule(mol, sel=None, idx=None):
        if (sel is not None and idx is not None) or (sel is None and idx is None):
            raise RuntimeError('Either sel or idx arguments must be used (and not both).')

        self = UniqueAtomID()
        if sel is not None:
            atom = mol.atomselect(sel, indexes=True)
        elif idx is not None:
            atom = np.array([idx, ])

        if len(atom) > 1:
            raise RuntimeError('Your atomselection returned more than one atom')
        if len(atom) == 0:
            raise RuntimeError('Your atomselection didn\'t match any atom')
        for f in UniqueAtomID._fields:
            setattr(self, f, getattr(mol, f)[atom][0])
        return self

    def selectAtom(self, mol, indexes=True, ignore=None):
        sel = np.ones(mol.numAtoms, dtype=bool)
        for f in UniqueAtomID._fields:
            if ignore is not None:
                ignore = ensurelist(ignore)
                if f in ignore:
                    continue
            sel &= getattr(mol, f) == getattr(self, f)

        if sum(sel) > 1:
            raise RuntimeError('The atom corresponding to {} is no longer unique in your '
                               'Molecule: {}'.format(self.__str__(), np.where(sel)[0]))
        if sum(sel) == 0:
            raise RuntimeError('The atom corresponding to {} is no longer present in your '
                               'Molecule'.format(self.__str__()))
        if indexes:
            return np.where(sel)[0][0]
        else:
            return sel

    def __eq__(self, other):
        iseq = True
        for f in UniqueAtomID._fields:
            iseq &= getattr(self, f, None) == getattr(other, f, None)
        return iseq

    def __str__(self):
        fieldvs = []
        for f in UniqueAtomID._fields:
            v = getattr(self, f, None)
            fieldvs.append('{}: {}'.format(f, '\'{}\''.format(v) if isinstance(v, str) else v))
        return 'UniqueAtomID<{}>'.format(', '.join(fieldvs))

    def __repr__(self):
        return '<{}.{} object at {}>\n'.format(self.__class__.__module__, self.__class__.__name__, hex(id(self))) \
               + self.__str__()


class UniqueResidueID:
    _fields = ('resname', 'chain', 'resid', 'insertion', 'segid')

    def __init__(self, **kwargs):
        """ Unique residue identifier

        Parameters
        ----------
        kwargs

        Examples
        --------
        >>> mol = Molecule('3ptb')
        >>> uqid = UniqueResidueID.fromMolecule(mol, 'resid 20')
        >>> uqid.selectAtoms(mol)
        array([23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34])
        >>> _ = mol.remove('resid 19')
        >>> uqid.selectAtoms(mol)
        array([19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30])
        """
        for key in kwargs:
            if key in UniqueAtomID._fields:
                setattr(self, key, kwargs[key])
            else:
                raise KeyError('Invalid key {}. The constructor only supports the '
                               'following fields: {}'.format(key, UniqueResidueID._fields))

    @staticmethod
    def fromMolecule(mol, sel=None, idx=None):
        if (sel is not None and idx is not None) or (sel is None and idx is None):
            raise RuntimeError('Only one of sel or idx arguments can be used.')

        self = UniqueResidueID()
        if sel is not None:
            atoms = mol.atomselect(sel, indexes=True)
            if len(atoms) == 0:
                raise RuntimeError('Your atomselection didn\'t match any residue')
        elif idx is not None:
            atoms = idx

        for f in UniqueResidueID._fields:
            vals = np.unique(getattr(mol, f)[atoms])
            if len(vals) != 1:
                raise RuntimeError('The atomselection gave more than one value: {} in field {} of mol'.format(vals, f))
            setattr(self, f, vals[0])
        return self

    def selectAtoms(self, mol, indexes=True, ignore=None):
        sel = np.ones(mol.numAtoms, dtype=bool)
        for f in UniqueResidueID._fields:
            if ignore is not None:
                ignore = ensurelist(ignore)
                if f in ignore:
                    continue
            sel &= getattr(mol, f) == getattr(self, f)

        if sum(sel) == 0:
            raise RuntimeError('The atoms corresponding to {} are no longer present in your '
                               'Molecule'.format(self.__str__()))

        if indexes:
            return np.where(sel)[0]
        else:
            return sel

    def __eq__(self, other):
        iseq = True
        for f in UniqueResidueID._fields:
            iseq &= getattr(self, f, None) == getattr(other, f, None)
        return iseq

    def __str__(self):
        fieldvs = []
        for f in UniqueResidueID._fields:
            v = getattr(self, f, None)
            fieldvs.append('{}: {}'.format(f, '\'{}\''.format(v) if isinstance(v, str) else v))
        return 'UniqueResidueID<{}>'.format(', '.join(fieldvs))

    def __repr__(self):
        return '<{}.{} object at {}>\n'.format(self.__class__.__module__, self.__class__.__name__, hex(id(self))) \
               + self.__str__()


def mol_equal(mol1, mol2, checkFields=Molecule._atom_and_coord_fields, exceptFields=None, fieldPrecision=None, _logger=True):
    """ Compare two Molecules for equality.

    Parameters
    ----------
    mol1 : Molecule
        The first molecule to compare
    mol2 : Molecule
        The second molecule to compare to the first
    checkFields : list
        A list of fields to compare. By default compares all atom information and coordinates in the molecule
    exceptFields : list
        A list of fields to not compare.
    fieldPrecision : dict
        A dictionary of `field`, `precision` key-value pairs which defines the numerical precision of the value comparisons of two arrays
    _logger : bool
        Set to False to disable the printing of the differences in the two Molecules

    Returns
    -------
    equal : bool
        Returns True if the molecules are equal or False if they are not.

    Examples
    --------
    >>> mol_equal(mol1, mol2, checkFields=['resname', 'resid', 'segid'])
    >>> mol_equal(mol1, mol2, exceptFields=['record', 'name'])
    >>> mol_equal(mol1, mol2, fieldPrecision={'coords': 1e-5})
    """
    difffields = []
    checkFields = list(checkFields)
    if exceptFields is not None:
        checkFields = np.setdiff1d(checkFields, exceptFields)
    for field in checkFields:
        field1 = field
        field2 = field

        if not hasattr(mol1, field) and hasattr(mol1, '_'+field):
            field1 = '_'+field
            if _logger: logger.warning('Could not find attribute {f} in mol1. Using attribute _{f}'.format(f=field))
        if not hasattr(mol2, field) and hasattr(mol2, '_'+field):
            field2 = '_'+field
            if _logger: logger.warning('Could not find attribute {f} in mol2. Using attribute _{f}'.format(f=field))

        
        if fieldPrecision is not None:
            precision = None
            if field1 in fieldPrecision:
                precision = fieldPrecision[field1]
            if field2 in fieldPrecision:
                precision = fieldPrecision[field2]
            if precision is not None and np.allclose(mol1.__getattribute__(field1), mol2.__getattribute__(field2), atol=precision):
                continue
                
        if not np.array_equal(mol1.__getattribute__(field1), mol2.__getattribute__(field2)):
            difffields += [field]

    if len(difffields) > 0:
        print('Differences detected in mol1 and mol2 in field(s) {}.'.format(difffields))
        return False
    return True


def _detectCollisions(mol1, frame1, mol2, frame2, gap):
    from scipy.spatial.distance import cdist

    distances = cdist(mol1.coords[:, :, frame1], mol2.coords[:, :, frame2])
    idx1, idx2 = np.where(distances < gap)

    return idx1, idx2


def _getResidueIndexesByAtom(mol, idx):
    from moleculekit.util import sequenceID
    seqid = sequenceID(mol.resid)
    allres = np.unique(seqid[idx])
    torem = np.zeros(len(seqid), dtype=bool)
    for r in allres:
        torem[seqid == r] = True
    return torem, len(allres)


def calculateUniqueBonds(bonds, bondtype):
    """ Given bonds and bondtypes calculates unique bonds dropping any duplicates

    Parameters
    ----------
    bonds : np.ndarray
        The bonds of a molecule
    bondtype : np.ndarray
        The bond type of each bond in the bonds array

    Returns
    -------
    uqbonds : np.ndarray
        The unique bonds of the molecule
    uqbondtype : np.ndarray
        The corresponding bond types for uqbonds

    Examples
    --------
    >>> from moleculekit.molecule import Molecule
    >>> mol = Molecule('3PTB')
    >>> mol.bonds, mol.bondtype = calculateUniqueBonds(mol.bonds, mol.bondtype)  # Overwrite the bonds and bondtypes with the unique ones
    """
    if bondtype is not None and len(bondtype):
        assert len(bondtype) == bonds.shape[0]
        # First sort all rows of the bonds array, then combine with bond types and find the unique rows [idx1, idx2, bondtype]
        unique_sorted = np.array(list(set(tuple(bb + [bt]) for bb, bt in zip(np.sort(bonds, axis=1).tolist(), bondtype.tolist()))))
        bonds = unique_sorted[:, :2].astype(np.uint32)
        bondtypes = unique_sorted[:, 2].astype(object)
        # Sort both arrays for prettiness by the first bond index
        sortidx = np.argsort(bonds[:, 0])
        return bonds[sortidx].copy(), bondtypes[sortidx].copy()
    else:
        bonds = np.array(list(set(tuple(bb) for bb in np.sort(bonds, axis=1).tolist())))
        sortidx = np.argsort(bonds[:, 0]) # Sort array for prettiness by the first bond index
        return bonds[sortidx].astype(np.uint32).copy(), None
    


class Representations:
    """ Class that stores representations for Molecule.

    Examples
    --------
    >>> from moleculekit.molecule import Molecule
    >>> mol = tryp.copy()
    >>> mol.reps.add('protein', 'NewCartoon')
    >>> print(mol.reps)                     # doctest: +NORMALIZE_WHITESPACE
    rep 0: sel='protein', style='NewCartoon', color='Name'
    >>> mol.view() # doctest: +SKIP
    >>> mol.reps.remove() # doctest: +SKIP
    """

    def __init__(self, mol):
        self.replist = []
        self._mol = mol
        return

    def append(self, reps):
        if not isinstance(reps, Representations):
            raise NameError('You can only append Representations objects.')
        self.replist += reps.replist

    def add(self, sel=None, style=None, color=None):
        """ Adds a new representation for Molecule.

        Parameters
        ----------
        sel : str
            Atom selection string for the representation.
            See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__
        style : str
            Representation style. See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node55.html>`__.
        color : str or int
            Coloring mode (str) or ColorID (int).
            See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node85.html>`__.
        """
        self.replist.append(_Representation(sel, style, color))

    def remove(self, index=None):
        """ Removed one or all representations.

        Parameters
        ----------
        index : int
            The index of the representation to delete. If none is given it deletes all.
        """
        if index is None:
            self.replist = []
        else:
            del self.replist[index]

    def list(self):
        """ Lists all representations. Equivalent to using print.
        """
        print(self)

    def __str__(self):
        s = ''
        for i, r in enumerate(self.replist):
            s += ('rep {}: sel=\'{}\', style=\'{}\', color=\'{}\'\n'.format(i, r.sel, r.style, r.color))
        return s

    def _translateNGL(self, rep):
        styletrans = {'newcartoon': 'cartoon', 'licorice': 'hyperball', 'lines': 'line', 'vdw': 'spacefill',
                      'cpk': 'ball+stick'}
        colortrans = {'name': 'element', 'index': 'residueindex', 'chain': 'chainindex', 'secondary structure': 'sstruc',
                      'colorid': 'color'}
        hexcolors = {0: '#0000ff', 1: '#ff0000', 2: '#333333', 3: '#ff6600', 4: '#ffff00', 5: '#4c4d00', 6: '#b2b2cc',
                     7: '#33cc33', 8: '#ffffff', 9: '#ff3399', 10: '#33ccff'}
        try:
            selidx = '@' + ','.join(map(str, self._mol.atomselect(rep.sel, indexes=True)))
        except:
            return None
        if rep.style.lower() in styletrans:
            style = styletrans[rep.style.lower()]
        else:
            style = rep.style
        if isinstance(rep.color, int):
            color = hexcolors[rep.color]
        elif rep.color.lower() in colortrans:
            color = colortrans[rep.color.lower()]
        else:
            color = rep.color
        return _Representation(sel=selidx, style=style, color=color)

    def _repsVMD(self, viewer):
        colortrans = {'secondary structure': 'Structure'}
        if len(self.replist) > 0:
            viewer.send('mol delrep 0 top')
            for rep in self.replist:
                if isinstance(rep.color, str) and rep.color.lower() in colortrans:
                    color = colortrans[rep.color.lower()]
                else:
                    color = rep.color
                viewer.send('mol selection {}'.format(rep.sel))
                viewer.send('mol representation {}'.format(rep.style))
                if isinstance(rep.color, str) and not rep.color.isnumeric():
                    viewer.send('mol color {}'.format(color))
                else:
                    viewer.send('mol color ColorID {}'.format(color))

                viewer.send('mol addrep top')

    def _repsNGL(self, viewer):
        if len(self.replist) > 0:
            reps = []
            for r in self.replist:
                r2 = self._translateNGL(r)
                if r2 is not None:
                    reps.append({"type": r2.style, "params": {"sele": r2.sel, "color": r2.color}})
            if reps != []:
                viewer.representations = reps


class _Representation:
    """ Class that stores a representation for Molecule

    Parameters
    ----------
    sel : str
        Atom selection for the representation.
        See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node89.html>`__
    style : str
        Representation style. See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node55.html>`__.
    color : str or int
        Coloring mode (str) or ColorID (int).
        See more `here <http://www.ks.uiuc.edu/Research/vmd/vmd-1.9.2/ug/node85.html>`__.

    Examples
    --------
    >>> r = _Representation(sel='protein', style='NewCartoon', color='Index')
    >>> r = _Representation(sel='resname MOL', style='Licorice')
    >>> r = _Representation(sel='ions', style='VDW', color=1)
    """

    def __init__(self, sel=None, style=None, color=None):
        if sel is not None:
            self.sel = sel
        else:
            self.sel = 'all'
        if style is not None:
            self.style = style
        else:
            self.style = 'Lines'
        if color is not None:
            self.color = color
        else:
            self.color = 'Name'

from unittest import TestCase
class _TestMolecule(TestCase):
    @classmethod
    def setUpClass(self):
        from moleculekit.home import home

        self.trajmol = Molecule(path.join(home(dataDir='test-molecule'), '3ptb_filtered.pdb'))
        self.trajmol.read(path.join(home(dataDir='test-molecule'), '3ptb_traj.xtc'))

        self.trajmollig = self.trajmol.copy()
        _ = self.trajmollig.filter('resname MOL')

        self.mol3PTB = Molecule('3PTB')

    def test_trajReadingAppending(self):
        from moleculekit.home import home
        # Testing trajectory reading and appending
        ref = Molecule(path.join(home(dataDir='test-molecule'), '3ptb_filtered.pdb'))
        xtcfile = path.join(home(dataDir='test-molecule'), '3ptb_traj.xtc')
        ref.read(xtcfile)
        assert ref.coords.shape == (4507, 3, 200)
        ref.read(xtcfile, append=True)
        assert ref.coords.shape == (4507, 3, 400)
        ref.read([xtcfile, xtcfile, xtcfile])
        assert ref.coords.shape == (4507, 3, 600)

    def test_guessBonds(self):
        # Checking bonds
        ref = self.trajmol.copy()
        ref.coords = np.atleast_3d(ref.coords[:, :, 0])
        len1 = len(ref._guessBonds())
        ref.coords = np.array(ref.coords, dtype=np.float32)
        len3 = len(ref._guessBonds())
        assert len1 == 4562
        assert len3 == 4562

    def test_setDihedral(self):
        # Testing dihedral setting
        mol = Molecule('2HBB')
        quad = [124, 125, 132, 133]
        mol.setDihedral(quad, np.deg2rad(-90))
        angle = mol.getDihedral(quad)
        assert np.abs(np.deg2rad(-90) - angle) < 1E-3

    def test_updateBondsAnglesDihedrals(self):
        from moleculekit.home import home

        # Testing updating of bonds, dihedrals and angles after filtering
        mol = Molecule(path.join(home(dataDir='test-molecule'), 'a1e.prmtop'))
        mol.read(path.join(home(dataDir='test-molecule'), 'a1e.pdb'))
        _ = mol.filter('not water')
        bb, bt, di, im, an = np.load(path.join(home(dataDir='test-molecule'), 'updatebondsanglesdihedrals_nowater.npy'), allow_pickle=True)
        assert np.array_equal(bb, mol.bonds)
        assert np.array_equal(bt, mol.bondtype)
        assert np.array_equal(di, mol.dihedrals)
        assert np.array_equal(im, mol.impropers)
        assert np.array_equal(an, mol.angles)
        _ = mol.filter('not index 8 18')
        bb, bt, di, im, an = np.load(
            path.join(home(dataDir='test-molecule'), 'updatebondsanglesdihedrals_remove8_18.npy'), allow_pickle=True)
        assert np.array_equal(bb, mol.bonds)
        assert np.array_equal(bt, mol.bondtype)
        assert np.array_equal(di, mol.dihedrals)
        assert np.array_equal(im, mol.impropers)
        assert np.array_equal(an, mol.angles)

    def test_appendingBondsBondtypes(self):
        from moleculekit.home import home

        # Testing appending of bonds and bondtypes
        mol = self.mol3PTB.copy()
        # TODO do not use parameterize data
        lig = Molecule(path.join(home(dataDir='test-molecule'), 'h2o2.mol2'))
        assert mol.bonds.shape[0] == len(mol.bondtype)  # Checking that Molecule fills in empty bondtypes
        newmol = Molecule()
        newmol.append(lig)
        newmol.append(mol)
        assert newmol.bonds.shape[0] == (mol.bonds.shape[0] + lig.bonds.shape[0])
        assert newmol.bonds.shape[0] == len(newmol.bondtype)

    def test_mdtrajWriter(self):
        # Testing MDtraj writer
        m = self.mol3PTB.copy()
        tmp = tempname(suffix='.h5')
        m.write(tmp, 'name CA')

    def test_uniqueAtomID(self):
        mol = self.mol3PTB.copy()
        uqid = UniqueAtomID.fromMolecule(mol, 'resid 20 and name CA')
        assert uqid.selectAtom(mol) == 24
        mol.remove('resid 19')
        assert uqid.selectAtom(mol) == 20
        a1 = UniqueAtomID.fromMolecule(mol, 'resid 20 and name CA')
        a2 = UniqueAtomID.fromMolecule(mol, idx=20)
        assert a1 == a2

    def test_uniqueResidueID(self):
        mol = self.mol3PTB.copy()
        uqid = UniqueResidueID.fromMolecule(mol, 'resid 20')
        assert np.array_equal(uqid.selectAtoms(mol), np.array([23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34]))
        mol.remove('resid 19')
        assert np.array_equal(uqid.selectAtoms(mol), np.array([19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30]))
        r1 = UniqueResidueID.fromMolecule(mol, 'resid 20 and name CA')
        r2 = UniqueResidueID.fromMolecule(mol, 'resid 20 and name CB')
        r3 = UniqueResidueID.fromMolecule(mol, 'resid 21 and name CA')
        assert r1 == r2
        assert r2 != r3

    def test_selfalign(self):
        from moleculekit.home import home

        # Checking bonds
        mol = self.trajmollig.copy()
        mol.align('noh')

        refcoords = np.load(path.join(home(dataDir='test-molecule'), 'test-selfalign-mol.npy'), allow_pickle=True)

        assert np.allclose(mol.coords, refcoords, atol=1E-3)

    def test_alignToReference(self):
        from moleculekit.home import home

        # Checking bonds
        mol = self.trajmollig.copy()

        mol2 = mol.copy()
        mol2.dropFrames(keep=3)  # Keep a random frame
        _ = mol2.filter('noh') # Remove some atoms to check aligning molecules with different numAtoms

        mol.align('noh', refmol=mol2)

        refcoords = np.load(path.join(home(dataDir='test-molecule'), 'test-align-refmol.npy'), allow_pickle=True)

        assert np.allclose(mol.coords, refcoords, atol=1E-3)
        assert np.allclose(mol.coords[mol.atomselect('noh'), :, 3], mol2.coords[:, :, 0], atol=1E-3)

    def test_alignToReferenceMatchingFrames(self):
        from moleculekit.home import home

        # Checking bonds
        mol = self.trajmollig.copy()

        mol2 = mol.copy()
        mol2.coords = np.roll(mol.coords, 3, axis=2)

        mol.align('noh', refmol=mol2, matchingframes=True)

        refcoords = np.load(path.join(home(dataDir='test-molecule'), 'test-align-refmol-matchingframes.npy'), allow_pickle=True)

        assert np.allclose(mol.coords, refcoords, atol=1E-3)

    def test_alignToReferenceSpecificFrames(self):
        from moleculekit.home import home

        # Checking bonds
        mol = self.trajmollig.copy()

        mol2 = mol.copy()
        mol2.dropFrames(keep=3)  # Keep a random frame
        _ = mol2.filter('noh') # Remove some atoms to check aligning molecules with different numAtoms

        originalcoords = mol.coords.copy()

        mol.align('noh', refmol=mol2, frames=[0, 1, 2, 3])

        refcoords = np.load(path.join(home(dataDir='test-molecule'), 'test-align-refmol-selectedframes.npy'), allow_pickle=True)

        assert np.allclose(originalcoords[:, :, 4:], mol.coords[:, :, 4:], atol=1E-3)
        assert np.allclose(mol.coords, refcoords, atol=1E-3)

    def test_reorderAtoms(self):
        mol = Molecule()
        mol.empty(8)
        mol.name[:] = ['C1', 'C3', 'H', 'O', 'S', 'N', 'H3', 'H1']
        randcoords = np.random.rand(8, 3, 1).astype(np.float32)
        mol.coords = randcoords.copy()
        mol.bonds = np.array([[0, 3], [1, 4], [7, 2]])
        mol.bondtype = np.array(['un', '1', '2'], dtype=object)
        mol.angles = np.array([[0, 3, 2], [1, 4, 6], [7, 2, 5]])
        mol.dihedrals = np.array([[0, 3, 1, 2], [1, 4, 2, 7], [7, 2, 1, 0]])
        mol.impropers = mol.dihedrals.copy()
        neworder = [1, 2, 4, 3, 0, 7, 5, 6]
        mol.reorderAtoms(neworder)
        assert np.array_equal(mol.name, ['C3', 'H', 'S', 'O', 'C1', 'H1', 'N', 'H3'])
        assert np.array_equal(mol.bonds, np.array([[4, 3], [0, 2], [5, 1]]))
        assert np.array_equal(mol.bondtype, ['un', '1', '2'])
        assert np.array_equal(mol.angles, np.array([[4, 3, 1], [0, 2, 7], [5, 1, 6]]))
        assert np.array_equal(mol.dihedrals, np.array([[4, 3, 0, 1], [0, 2, 1, 5], [5, 1, 0, 4]]))
        assert np.array_equal(mol.impropers, np.array([[4, 3, 0, 1], [0, 2, 1, 5], [5, 1, 0, 4]]))
        assert np.array_equal(mol.coords, randcoords[neworder])

    def test_sequence(self):
        refseq = 'IVGGYTCGANTVPYQVSLNSGYHFCGGSLINSQWVVSAAHCYKSGIQVRLGEDNINVVEGNEQFISASKSIVHPSYNSNTLNNDIMLIKLKSAASLNSRVASISLPTSCASAGTQCLISGWGNTKSSGTSYPDVLKCLKAPILSDSSCKSAYPGQITSNMFCAGYLEGGKDSCQGDSGGPVVCSGKLQGIVSWGSGCAQKNKPGVYTKVCNYVSWIKQTIASN'
        assert self.mol3PTB.sequence()['0'] == refseq

    def test_appendFrames(self):
        trajmol = self.trajmol.copy()
        nframes = trajmol.numFrames
        trajmol.appendFrames(trajmol)
        assert trajmol.numFrames == (2 * nframes) 

    def test_renumberResidues(self):
        from moleculekit.home import home
        mol = self.mol3PTB.copy()
        mapping = mol.renumberResidues(returnMapping=True)
        refres = np.load(os.path.join(home(dataDir='test-molecule'), 'renumberedresidues.npy'), allow_pickle=True)
        assert np.array_equal(mol.resid, refres)

    def test_str_repr(self):
        assert len(self.__str__()) != 0
        assert len(self.__repr__()) != 0

    def test_mol_equal(self):
        assert mol_equal(self.mol3PTB, self.mol3PTB)
        assert not mol_equal(self.mol3PTB, self.trajmol)

    def test_mol_equal_precision(self):
        mol1 = self.mol3PTB
        mol2 = self.mol3PTB.copy()
        mol2.coords += 0.001
        assert mol_equal(mol1, mol2, fieldPrecision={'coords': 1e-2})
        assert not mol_equal(mol1, mol2, fieldPrecision={'coords': 1e-4})



if __name__ == "__main__":
    # Unfortunately, tests affect each other because only a shallow copy is done before each test, so
    # I do a 'copy' before each.
    import doctest
    import unittest

    m = Molecule('3PTB')
    doctest.testmod(extraglobs={'tryp': m.copy()})

    unittest.main(verbosity=2)






