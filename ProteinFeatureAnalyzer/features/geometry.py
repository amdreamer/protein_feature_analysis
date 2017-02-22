import numpy as np
import scipy
import scipy.spatial
import Bio.PDB as PDB


def get_phi(chain, residue):
  '''Calculate the phi torsion of a residue.'''
  
  # Get the previous residue

  res_id = residue.get_id()
  prev_res = chain[res_id[1] - 1]
  
  prev_flag = prev_res.get_id()[0]
  if prev_flag == 'W' or prev_flag.startswith('H_'):
    raise Exception('Hetero residue type!')
 
  # Calculate the torsion

  c_prev = prev_res['C'].get_vector()
  n = residue['N'].get_vector()
  ca = residue['CA'].get_vector()
  c = residue['C'].get_vector()

  return PDB.calc_dihedral(c_prev, n, ca, c) 

def get_psi(chain, residue):
  '''Calculate the psi torsion of a residue.'''
  
  # Get the next residue

  res_id = residue.get_id()
  next_res = chain[res_id[1] + 1]
  
  next_flag = next_res.get_id()[0]
  if next_flag == 'W' or next_flag.startswith('H_'):
    raise Exception('Hetero residue type!')
  
  # Calculate the torsion

  n = residue['N'].get_vector()
  ca = residue['CA'].get_vector()
  c = residue['C'].get_vector()
  n_next = next_res['N'].get_vector()

  return PDB.calc_dihedral(n, ca, c, n_next)

def get_distance_matrix(atom_list):
  '''Get the distance matrix of a list of atoms.'''
  return scipy.spatial.distance.squareform(scipy.spatial.distance.pdist(
      np.array([a.get_coord() for a in atom_list]), 'euclidean'))

def get_nearest_nonbonded_residues(model):
  '''Return a list of 2-tuples. Each the first element of each tuple is a
  residue and the second element is its nearest nonbonded residue.'''
 
  # Get all CA atoms which are used to be the center of residues

  ca_list = []
  
  for residue in model.get_residues():
    flag = residue.get_id()[0]
    if flag == 'W' or flag.startswith('H_'): continue
    
    for a in residue:
      if a.get_id() == 'CA':
        ca_list.append(a)

  ca_coords = [a.get_coord() for a in ca_list]

  # Make a KDTree for neighbor searching

  kd_tree = scipy.spatial.KDTree(ca_coords)

  # Find the nearest nonbonded neighbor of all residues

  nearest_nb_list = []

  for i in range(len(ca_list)):
    res1 = ca_list[i].get_parent()
    distance, indices = kd_tree.query(ca_coords[i], k=4)

    for j in range(1, 4):
      res2 = ca_list[indices[j]].get_parent() 

      if res1.get_parent().get_id() == res2.get_parent().get_id() \
         and (res1.get_id()[1] + 1 == res2.get_id()[1] \
         or res1.get_id()[1] - 1 == res2.get_id()[1]) : # Bonded residues
           continue
    
    nearest_nb_list.append((res1, res2))   

  return nearest_nb_list

def normalize(v):
  '''Normalize a numpy array.'''
  norm=np.linalg.norm(v)
  if norm==0: 
     return v
  return v/norm

def get_residue_stub_matrix(residue):
  '''Constructure a coordinate frame on a residue. The origin is on the CA atom; 
  the x-axis is from CA to N; the z-axis is the cross product of the x-axis and the
  CA-C vector; the y-axis is thus defined by requiring the frame to be right handed.
  Return a 3x3 matrix and a vector that transforms coordinates in the local frame to 
  coordinates in the global frame.
  '''
  n = residue['N'].get_coord()
  ca = residue['CA'].get_coord()
  c = residue['C'].get_coord()

  x = normalize(n - ca)
  z = normalize(np.cross(x, c - ca))
  y = np.cross(z, x)

  return np.matrix([x, y, z]).T, ca

def rotation_matrix_to_euler_angles(m):
  '''Return the euler angles corresponding to a rotation matrix.'''
  theta_x = np.arctan2(m[2][1], m[2][2])
  theta_y = np.arctan2(-m[2][0], np.sqrt(m[2][1]**2 + m[2][2]**2))
  theta_z = np.arctan2(m[1][0], m[0][0])

  return theta_x, theta_y, theta_z

def euler_angles_to_rotation_matrix(theta_x, theta_y, theta_z):
  '''Return the rotation matrix corresponding to 3 Euler angles.'''
  cx = np.cos(theta_x)
  sx = np.sin(theta_x)
  cy = np.cos(theta_y)
  sy = np.sin(theta_y)
  cz = np.cos(theta_z)
  sz = np.sin(theta_z)
  
  X = np.array([[  1,   0,   0],
                [  0,  cx, -sx],
                [  0,  sx,  cx]])
  Y = np.array([[ cy,   0,  sy],
                [  0,   1,   0],
                [-sy,   0,  cy]])
  Z = np.array([[ cz, -sz,   0],
                [ sz,  cz,   0],
                [  0,   0,   1]])

  return np.matmul(Z, np.matmul(Y, X))

def random_unit_vector(dim=3):
  '''Generate a random unit vector following the
  uniform distribution on the (dim - 1) dimension sphere.
  '''
  while True:
    v = np.random.normal(size=dim)
    if np.linalg.norm(v) > 0: break
  
  return normalize(v)

def random_rotation_matrix():
  '''Generate a random rotation matrix following the
  uniform distribution in SO(3).
  '''
  x = random_unit_vector()
  t = random_unit_vector()
  while np.linalg.norm(x - t) == 0:
    t = random_unit_vector()
  y = normalize(np.cross(x, t))
  z = np.cross(x, y)

  return np.array([x, y, z])

def random_euler_angles():
  '''Generate a random euler angles following the
  uniform distribution in SO(3).
  '''
  return rotation_matrix_to_euler_angles(random_rotation_matrix())
