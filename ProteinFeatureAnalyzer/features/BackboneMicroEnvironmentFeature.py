import os

import numpy as np
import pandas as pd
from sklearn import svm
from sklearn.ensemble import IsolationForest
from sklearn import mixture
import matplotlib
matplotlib.use('TkAgg') 
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import axes3d

from .Feature import Feature
from . import data_loading
from . import geometry
from . import machine_learning


class BackboneMicroEnvironmentFeature(Feature):
  '''The BackboneMicroEnvironmentFeature analyzes the micro environments
  of backbones of each residue. The micro environemt is formed by the residue
  it self and its nearest non-connected residue.'''
  
  def __init__(self):
    super().__init__()
  
  def extract(self, input_path, total_num_threads=1, my_id=0):
    '''Extract features from structures in the input path.'''
    for f in self.list_my_jobs(input_path, total_num_threads, my_id):
      if f.endswith('.pdb'):
        self.extract_from_one_file(os.path.join(input_path, f))

  def extract_from_one_file(self, pdb_file):
    structure = data_loading.structure_from_pdb_file(pdb_file)
  
    for model in structure:
      nearest_nb_list = geometry.get_nearest_nonbonded_residues(model)
   
      for res1, res2 in nearest_nb_list:
        feature_dict ={}
        
        # Get the torsions
        
        try:
          feature_dict['phi1'] = geometry.get_phi(res1.get_parent(), res1) 
          feature_dict['psi1'] = geometry.get_psi(res1.get_parent(), res1) 
          feature_dict['phi2'] = geometry.get_phi(res2.get_parent(), res2) 
          feature_dict['psi2'] = geometry.get_psi(res2.get_parent(), res2) 
        except:
          continue

        # Get the relative position of the second residue 

        s_matrix, origin = geometry.get_residue_stub_matrix(res1)
        shift_global = res2['CA'].get_coord() - res1['CA'].get_coord()
        feature_dict['shift'] = np.matmul(np.array(s_matrix.T), np.array(shift_global))

        # Get the relative orientation of the second residue

        s_matrix2, origin2 = geometry.get_residue_stub_matrix(res2)
        rot_matrix = np.dot(s_matrix.T, s_matrix2) # Rotation matrix in the frame of the first residue
        feature_dict['theta_x'], feature_dict['theta_y'], feature_dict['theta_z'] = \
                geometry.rotation_matrix_to_euler_angles(np.array(rot_matrix))

        self.feature_list.append(feature_dict)

    #print(self.feature_list)

  def save(self, data_path):
    '''Save the data into a csv file.'''
    data = [ (d['phi1'], d['psi1'], d['phi2'], d['psi2'], d['shift'][0], d['shift'][1], d['shift'][2],
            d['theta_x'], d['theta_y'], d['theta_z']) 
            for d in self.feature_list ]
    df = pd.DataFrame(data)
    
    self.append_to_csv(df, os.path.join(data_path, 'bb_micro_env_features.csv'))

  def load(self, data_path):
    '''Load data from a csv file.'''
    df = pd.read_csv(os.path.join(data_path, 'bb_micro_env_features.csv'), header=None)
    
    for index, row in df.iterrows():
      self.feature_list.append({'phi1':row[0], 'psi1':row[1], 'phi2':row[2], 'psi2':row[3],
          'shift':np.array([row[4], row[5], row[6]]), 'theta_x':row[7], 'theta_y':row[8], 'theta_z':row[9] })

  def feature_dict_to_machine_learning_features(self, feature_dict):
    '''Given a feature dictionary, return its corresponding features
    for machine learning. To ensure the topologies of features, the torsion
    angles need to be expanded to their cos() and sin(). The three euler angles
    should be expanded to a 9-dim rotation matrix.
    (Alas, the unit quaterions is diffeomorphic to S3, so its not homomorphic
    to SO(3).)
    '''
    return machine_learning.angle_to_cos_sin(feature_dict['phi1']) \
            + machine_learning.angle_to_cos_sin(feature_dict['psi1']) \
            + machine_learning.angle_to_cos_sin(feature_dict['phi2']) \
            + machine_learning.angle_to_cos_sin(feature_dict['psi2']) \
            + list(feature_dict['shift']) \
            + list(geometry.euler_angles_to_rotation_matrix(feature_dict['theta_x'],
                feature_dict['theta_y'], feature_dict['theta_z']).reshape(9))

  def transform_features(self, feature_list):
    '''Transform feature representations. The arguement feature_list
    could be a list of dictionary or a list of list.
    '''
    if isinstance(feature_list[0], dict):
      return [self.feature_dict_to_machine_learning_features(d) for d in feature_list]
    
    else:
      return [machine_learning.angle_to_cos_sin(d[0]) + machine_learning.angle_to_cos_sin(d[1]) \
            + machine_learning.angle_to_cos_sin(d[2]) + machine_learning.angle_to_cos_sin(d[3]) \
            + list(d[4]) \
            + list(geometry.euler_angles_to_rotation_matrix(d[5], d[6], d[7]).reshape(9))
            for d in feature_list]

  def learn(self, clf_type="OneClassSVM", transform_features=False):
    '''Train a machine learning classifier on the features.'''
   
    all_data = [[d['phi1'], d['psi1'], d['phi2'], d['psi2']] + list(d['shift']) + [d['theta_x'], d['theta_y'], d['theta_z']]
            for d in self.feature_list]
    if transform_features:
      all_data = self.transform_features(self.feature_list)
    n_data = len(all_data)

    training_data = all_data[0:int(0.6 * n_data)]
    test_data = all_data[int(0.6 * n_data):int(0.8 * n_data)]
    cv_data = all_data[int(0.8 * n_data):n_data]
  
    # Train the classifier
    
    if clf_type == "OneClassSVM":
      nus = [0.05, 0.02, 0.01, 0.005, 0.002, 0.001]
      least_error = len(test_data)

      for i in range(len(nus)):
        print("nu = {0}".format(nus[i]))

        clf = svm.OneClassSVM(nu=nus[i], kernel="rbf", gamma='auto')
        clf.fit(training_data)
        
        predictions = clf.predict(training_data)
        print("{0}/{1} training error.".format(len(predictions[-1 == predictions]), len(training_data)))
        
        predictions = clf.predict(test_data)
        print("{0}/{1} test error.\n".format(len(predictions[-1 == predictions]), len(test_data)))

        if len(predictions[-1 == predictions]) < least_error:
          least_error = len(predictions[-1 == predictions])
          self.clf = clf
    
    elif clf_type == "IsolationForest": 
      self.clf = IsolationForest(max_samples=50000,
			contamination=0.05, random_state=np.random.RandomState(42))
      self.clf.fit(training_data)
   
    # Print Training results
    
    predictions = self.clf.predict(cv_data)
    print("{0}/{1} cross validation error.".format(len(predictions[-1 == predictions]), len(cv_data)))
    
    if clf_type == "OneClassSVM":
      print("{0} support vectors found.".format(len(self.clf.support_)))

  def predict(self, input_data, transform_features=False):
    '''Make a prediction for the input data with the machine learning classifier.
    input_data is a list of (phi1, psi1, phi2, psi2, [shift], theta_x, theta_y, theta_z].
    '''
    transformed_data = [[d[0], d[1], d[2], d[3]] + list(d[4]) + [d[5], d[6], d[7]]
            for d in input_data] 
    
    if transform_features:
      transformed_data = self.transform_features(input_data) 
    return self.clf.predict(transformed_data)

  def generate_random_features(self, NUM_SAMPLES=10000):
    '''Generate a list of random features.'''

    phis1 = np.random.uniform(-np.pi, np.pi, NUM_SAMPLES)
    psis1 = np.random.uniform(-np.pi, np.pi, NUM_SAMPLES)
    phis2 = np.random.uniform(-np.pi, np.pi, NUM_SAMPLES)
    psis2 = np.random.uniform(-np.pi, np.pi, NUM_SAMPLES)
    shifts = [None] * NUM_SAMPLES
    txs = [None] * NUM_SAMPLES
    tys = [None] * NUM_SAMPLES
    tzs = [None] * NUM_SAMPLES
    for i in range(NUM_SAMPLES):
      shifts[i] = np.random.uniform(3.5, 6) * geometry.random_unit_vector()
      txs[i], tys[i], tzs[i] = geometry.random_euler_angles()

    return list(zip(phis1, psis1, phis2, psis2, shifts, txs, tys, tzs))

  def calculate_space_reduction(self, transform_features=False):
    '''Calculate the space reduction power of the machine learning model.'''
    predictions = self.predict(self.generate_random_features(), transform_features=transform_features)
    print("The space is reduced by {0}.".format(len(predictions[1 == predictions]) / len(predictions)))

  def density_estimate(self, de_type="GaussianMixture", transform_features=True):
    '''Get a density estimation of the data.'''
    all_data = [[d['phi1'], d['psi1'], d['phi2'], d['psi2']] + list(d['shift']) + [d['theta_x'], d['theta_y'], d['theta_z']]
            for d in self.feature_list]
    if transform_features:
      all_data = self.transform_features(self.feature_list)
    n_data = len(all_data)

    training_data = all_data[0:int(0.7 * n_data)]
    test_data = all_data[int(0.7 * n_data):n_data]
    
    # Make some random data
    
    random_data = self.generate_random_features()
    if transform_features: 
        random_data = self.transform_features(random_data)
    
    if de_type == "GaussianMixture":
      self.de = mixture.BayesianGaussianMixture(n_components=1000, covariance_type='full').fit(training_data)
      
      # Evalute the cumulative distribution functions of scores of test data

      test_scores = self.de.score_samples(test_data)
      values, base = np.histogram(test_scores, bins=40)
      cumulative = np.cumsum(values)

      for i in range(40):
          
        # Evaluate the space compression

        random_scores = self.de.score_samples(random_data)
        compress_coe = len(random_scores[random_scores > base[i]]) / len(random_scores)
          
        print('{0:.3f}\t{1}\t{2:.5f}\t{3:.5f}'.format(base[i], cumulative[i], cumulative[i] / len(test_data), compress_coe))

  def visualize(self):
    pass

  def plot_nearst_nonbonded_list(self, nearest_nb_list):
    '''A debugging function to print the nearest nonbonded residue list.'''
    X = [pair[0]['CA'].get_coord()[0] for pair in nearest_nb_list]
    Y = [pair[0]['CA'].get_coord()[1] for pair in nearest_nb_list]
    Z = [pair[0]['CA'].get_coord()[2] for pair in nearest_nb_list]
    
    U = [pair[1]['CA'].get_coord()[0] - pair[0]['CA'].get_coord()[0] for pair in nearest_nb_list]
    V = [pair[1]['CA'].get_coord()[1] - pair[0]['CA'].get_coord()[1] for pair in nearest_nb_list]
    W = [pair[1]['CA'].get_coord()[2] - pair[0]['CA'].get_coord()[2] for pair in nearest_nb_list]

    fig = plt.figure()
    ax = fig.gca(projection='3d')
    ax.quiver(X, Y, Z, U, V, W)
    plt.show()

  def plot_shifts(self):
    '''Plot the distribution of the translational shifts from the 
    CA atom of the first residue to the CA atom of the second residue.
    '''

    # Data points

    X = [d['shift'][0] for d in self.feature_list]
    Y = [d['shift'][1] for d in self.feature_list]
    Z = [d['shift'][2] for d in self.feature_list]

    # Postions of N and C

    n_ca_c_angle = 110.86 * np.pi / 180

    fig =plt.figure()
    ax = fig.gca(projection='3d')
    ax.scatter(X, Y, Z, c='green', s=5)
    ax.quiver([0], [0], [0], [1.32869], [0], [0], color='blue')
    ax.quiver([0], [0], [0], [1.52326 * np.cos(n_ca_c_angle)], [1.52326 * np.sin(n_ca_c_angle)], [0], color='red')

    plt.show()

  def plot_shift_length_histogram(self):
    '''Plot a histogram of the lengths of translational shifts.'''

    lengths = [np.linalg.norm(d['shift']) for d in self.feature_list]
    hist, bin_edges = np.histogram(lengths, bins=0.5 * np.arange(20))

    plt.bar(bin_edges[0:-1] - 0.25, hist, width=0.5, edgecolor='black')
    plt.show()

  def scatter_plot_two_features(self, feature1_l, feature2_l, axis=None):
    '''Make a scatter plot of two features. feature1_l and feature2_l
    are lambda expressions for pick a feature.
    '''

    f1 = [feature1_l(d) for d in self.feature_list]
    f2 = [feature2_l(d) for d in self.feature_list]

    plt.scatter(f1, f2, s=5)
    if axis:
      plt.axis(axis)
    plt.show()

  def scatter_plot_three_features(self, feature1_l, feature2_l, feature3_l, axis=None):
    '''Make a scatter plot of three features, given their lambda expressions.'''

    f1 = [feature1_l(d) for d in self.feature_list]
    f2 = [feature2_l(d) for d in self.feature_list]
    f3 = [feature3_l(d) for d in self.feature_list]

    fig = plt.figure()
    ax = fig.gca(projection='3d')
    ax.scatter(f1, f2, f3, s=5)

    if axis:
      ax.set_xlim(axis[0], axis[1])
      ax.set_ylim(axis[2], axis[3])
      ax.set_zlim(axis[4], axis[5])

    plt.show()
