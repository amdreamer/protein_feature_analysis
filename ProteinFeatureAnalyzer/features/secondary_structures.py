import subprocess

import numpy as np
import Bio.PDB as PDB
import networkx as nx

from . import geometry


def make_dssp_dict(pdb_path, dssp_path):
  '''Make a dictionary that stores the DSSP information of a
  protein. The keys are (chain_id, res_id).

  Return values:
    - a DSSP information dictionary
    - a map from dssp sequential number to keys
  '''
  # Get the DSSP outputs

  p = subprocess.Popen([dssp_path, pdb_path], universal_newlines=True,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  out, err = p.communicate()
  
  # Report error
  
  if err.strip():
    warnings.warn(err)
    if not out.strip():
      raise Exception('DSSP failed to produce an output')

  # Parse the DSSP output

  lines = out.split('\n')
  i = 0

  # Ignore the headers

  while len(lines[i].split()) < 2 or lines[i].split()[1] != 'RESIDUE':
    i += 1

  # Parse line by line

  dssp_dict = {}
  key_map = {}

  for l in lines[i + 1:]:
    if len(l.strip()) == 0: continue
    if l[9] == " ":
            # Skip -- missing residue
            continue

    seq_num = int(l[0:5])   # Sequential residue number,including chain breaks as extra residues
    res_id = int(l[5:10])   # Residue ID in PDB file
    chain_id = l[11]        # Chain ID
    ss = l[16]              # Secondary structure
    bbl1 = l[23]            # Beta bridge label 1
    bbl2 = l[24]            # Beta bridge label 2
    bp1 = int(l[26:29])     # Beta bridge partner 1
    bp2 = int(l[30:33])     # Beta bridge partner 2
    bsl = l[33]             # Beta sheet label
    nh_to_o1 = l[39:50].split(',')     # Hydrogen bond from NH to O 1
    o_to_nh1 = l[50:61].split(',')     # Hydrogen bond from O to NH 1
    nh_to_o2 = l[61:72].split(',')     # Hydrogen bond from NH to O 2
    o_to_nh2 = l[72:83].split(',')     # Hydrogen bond from O to NH 2

    key_map[seq_num] = (chain_id, res_id)
    dssp_dict[(chain_id, res_id)] = {'seq_num':seq_num, 'ss':ss,
            'bbl1':bbl1, 'bbl2':bbl2, 'bp1':bp1, 'bp2':bp2, 'bsl':bsl,
            'nh_to_o1':(int(nh_to_o1[0]), float(nh_to_o1[1])),
            'o_to_nh1':(int(o_to_nh1[0]), float(o_to_nh1[1])),
            'nh_to_o2':(int(nh_to_o2[0]), float(nh_to_o2[1])),
            'o_to_nh2':(int(o_to_nh2[0]), float(o_to_nh2[1])) }

  return dssp_dict, key_map


def pack_dssp_dict_into_ss_list(model, dssp_dict, key_map):
  '''Pack a dssp dictionary into a list of secondary structures
  and a list of beta sheets.
  '''
 
  # map to translate secondary structures

  ss_map = {'H':'H', 'B':'B', 'E':'E', 'G':'G', 'I':'I', 'T':'T'}

  def same_ss(dssp_dict, key1, key2):
    '''Return if two residues have save secondary structures.
    Bend are regarded as normal loops.
    Note that for beta strands, they should be in the same sheet
    to be considered the same.
    '''
    return ss_map.setdefault(dssp_dict[key1]['ss'], ' ') == ss_map.setdefault(dssp_dict[key2]['ss'], ' ') \
            and dssp_dict[key1]['bsl'] == dssp_dict[key2]['bsl']


  # Get the list of secondary structures
  
  ss_list = []

  for chain in model:
    c_id = chain.get_id()

    residue_list = [r for r in chain]

    start = 0
    while start < len(residue_list):
      start_r_id = residue_list[start].get_id()[1]
      start_ss = dssp_dict[(c_id, start_r_id)]['ss']

      # Find the stop position of the secondary structure

      stop = start + 1
      while stop < len(residue_list):
        stop_r_id = residue_list[stop].get_id()[1]
        
        if not same_ss(dssp_dict, (c_id, start_r_id), (c_id, stop_r_id)):
          break
        stop += 1

      stop -= 1

      # Add the secondary structure into a list

      ss_residue_list = [residue_list[i] for i in range(start, stop + 1)] 

      if 'H' == start_ss:
        ss_list.append(AlphaHelix(ss_residue_list))
      
      elif 'E' == start_ss or 'B' == start_ss:
        ss_list.append(BetaStrand(ss_residue_list, dssp_dict[(c_id, start_r_id)]['bsl']))
      
      else:
        ss_list.append(Loop(ss_residue_list, ss_map.setdefault(start_ss, ' ')))

      start = stop + 1

  # Get the list of beta sheets

  sheet_list = []
  sheet_id_set = set()
  for ss in ss_list:
    if isinstance(ss, BetaStrand):
      sheet_id_set.add(ss.sheet_id)

  for sheet_id in sheet_id_set:  
    sheet_list.append(BetaSheet(sheet_id, 
        [ss for ss in ss_list if isinstance(ss, BetaStrand) and ss.sheet_id == sheet_id],
        dssp_dict, key_map, model))

  return ss_list, sheet_list

class SecondaryStructure:
  '''Base class for secondary structures.'''
  def __init__(self):
    pass

class AlphaHelix(SecondaryStructure):
  '''Class that represents an alpha helix.'''
  def __init__(self, residue_list):
    self.residue_list = residue_list

class BetaStrand(SecondaryStructure):
  '''Class that represents a beta strand.'''
  def __init__(self, residue_list, sheet_id):
    self.residue_list = residue_list
    self.sheet_id = sheet_id

class BetaSheet(SecondaryStructure):
  '''Class that represents a beta sheet.'''
  def __init__(self, sheet_id, strand_list, dssp_dict, key_map, model):
    self.sheet_id = sheet_id
    self.strand_list = strand_list
    self.init_sheet_graph(dssp_dict, key_map, model)

  def init_sheet_graph(self, dssp_dict, key_map, model):
    '''Initialize a graph to represent a beta sheet.'''
    self.graph = nx.MultiDiGraph()

    # Add the strands

    for strand in self.strand_list:
      for i in range(len(strand.residue_list) - 1):
        self.graph.add_edge(strand.residue_list[i],
                strand.residue_list[i + 1], edge_type='pp_bond')
    
    # Add the hydrogen bonds

    residues = [res for strand in self.strand_list for res in strand.residue_list]

    for res in residues:
      d = dssp_dict[(res.get_parent().get_id(), res.get_id()[1])]

      # Add a hydrogen bond if the H bond energy is below a limit

      HB_ENERGY_LIMIT = -1.5

      if d['nh_to_o1'][1] < HB_ENERGY_LIMIT:
        key = key_map[d['seq_num'] + d['nh_to_o1'][0]]
        res2 = model[key[0]][key[1]]
        
        if res2 in residues:
          self.graph.add_edge(res, res2, edge_type='nh_to_o1')
        
      if d['o_to_nh1'][1] < HB_ENERGY_LIMIT:
        key = key_map[d['seq_num'] + d['o_to_nh1'][0]]
        res2 = model[key[0]][key[1]]
        
        if res2 in residues:
          self.graph.add_edge(res, res2, edge_type='o_to_nh1')
        
      if d['nh_to_o2'][1] < HB_ENERGY_LIMIT:
        key = key_map[d['seq_num'] + d['nh_to_o2'][0]]
        res2 = model[key[0]][key[1]]
        
        if res2 in residues:
          self.graph.add_edge(res, res2, edge_type='nh_to_o2')
        
      if d['o_to_nh2'][1] < HB_ENERGY_LIMIT:
        key = key_map[d['seq_num'] + d['o_to_nh2'][0]]
        res2 = model[key[0]][key[1]]
        
        if res2 in residues:
          self.graph.add_edge(res, res2, edge_type='o_to_nh2')

class Loop(SecondaryStructure):
  '''Class that represents a loop.'''
  def __init__(self, residue_list, ss_type):
    self.residue_list = residue_list
    self.type = ss_type

