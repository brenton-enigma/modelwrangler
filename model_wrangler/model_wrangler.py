"""
Module implements the base class for tensorflow models, TfModel
"""

import os
import logging
import json

import numpy as np
import tensorflow as tf

from tf_models import BaseNetwork
from dataset_managers import DatasetManager

class ModelParams(object):
    """Parse the model params opts passed in as kwargs
    """

    # all params are stored as attributes, so we need pylint to
    # shut up about having too many instance attributes.
    #
    # pylint: disable=too-many-instance-attributes

    def __init__(self, kwargs):

        self.verb = kwargs.get('verb', True)
        self.name = kwargs.get('name', 'newmodel')
        self.path = kwargs.get(
            'path',
            os.path.join(os.path.curdir, self.name)
        )

        logging.basicConfig(
            filename=os.path.join(self.path, '{}.log'.format(self.name)),
            level=logging.INFO)

        # model params
        self.in_size = kwargs.get('in_size', 10)
        self.out_size = kwargs.get('out_size', 3)

        # training params
        self.max_iter = kwargs.get('max_iter', 500)
        self.batch_size = kwargs.get('batch_size', 250)
        self.num_epoch = kwargs.get('num_epoch', 2)

    def init_save_dir(self):
        """Initialize save dir
        """
        logging.info('Save directory : %s', self.path)

        try:
            os.makedirs(self.path)
        except OSError:
            logging.warn('Save directory already exists')

    def find_metagraph(self):
        """Find the most recent meta file with this model
        """
        meta_list = os.path.join(self.path, '*.meta')
        newest_meta_file = max(meta_list, key=os.path.getctime)
        return newest_meta_file

    def save(self):
        """save model params to JSON
        """

        self.init_save_dir()

        params_fname = os.path.join(
            self.path,
            '-'.join([self.name, 'params.json'])
            )
        logging.info('Saving parameter file %s', params_fname)

        with open(params_fname, 'wt') as json_file:
            json.dump(
                vars(self),
                json_file,
                ensure_ascii=True,
                indent=4)


class ModelWrangler(object):
    """

    Loads a model (Default is `BaseModel`) and wraps it with a bunch of helpful
    functions:

        - `save` save tf model to disk
        - `restore` bring a trained model back from the dead (i.e. load from disk)

        - `predict` get model activations for a given input        
        - `score` get model model loss for a set of inputs and target outputs
        - `feature_importance` estimate feature importance by looking at error
            gradients for a set of inputs and target outputs
    """

    def __init__(self, model_type=BaseNetwork, **kwargs):
        """Initialize a tensorflow model
        """
        self.params = ModelParams(kwargs)
        self.tf_mod = model_type(self.params)

    def save(self, iteration):
        """Save model parameters in a JSON and model weights in TF format
        """

        self.params.save()

        logging.info('Saving weights file in %s', self.params.path)
        with tf.Session(graph=self.tf_mod.graph) as sess:
            self.tf_mod.saver.save(
                sess,
                save_path=self.params.path,
                global_step=iteration,
            )

    @classmethod
    def load(cls, param_file):
        """restore a saved model given the path to a paramter JSON file
        """

        # load model params
        with open(param_file, 'rt') as pfile:
            params = json.load(pfile)

        # initialize a new model, restore its weights
        new_model = cls(**params)

        # restore weights
        new_model.tf_mod.saver = tf.train.import_meta_graph(new_model.params.find_metagraph())
        last_checkpoint = tf.train.latest_checkpoint(new_model.params.path)

        with tf.Session(graph=new_model.tf_mod.graph) as sess:
            new_model.tf_mod.saver.restore(sess, last_checkpoint)

        return new_model

    def predict(self, input_x):
        """
        Get activations for every layer given an input matrix, input_x
        """
        data_dict = {
            self.tf_mod.input: input_x,
            self.tf_mod.is_training: False
        }

        with tf.Session(graph=self.tf_mod.graph) as sess:
            vals = sess.run(self.tf_mod.output, feed_dict=data_dict)

        return vals

    def score(self, input_x, target_y, score_func=None):
        """
        Measure model's current performance
        for a set of input_x and target_y using some scoring function
        `score_func` (defults to model loss function)
        """

        data_dict = {
            self.tf_mod.input: input_x,
            self.tf_mod.target: target_y,
            self.tf_mod.is_training: False
        }

        if score_func is None:
            score_func = self.tf_mod.loss

        with tf.Session(graph=self.tf_mod.graph) as sess:
            val = score_func.eval(feed_dict=data_dict, session=sess)

        return val

    def feature_importance(self, input_x, target_y, score_func=None):
        """Calculate feature importances"""

        # which layer has the features you care about?
        feature_layer_idx = 0

        data_dict = {
            self.tf_mod.input: input_x,
            self.tf_mod.target: target_y,
            self.tf_mod.is_training: False
        }

        if score_func is None:
            score_func = self.tf_mod.loss

        grad_wrt_input = tf.gradients(
            score_func,
            self.tf_mod.input
        )

        with tf.Session(graph=self.tf_mod.graph) as sess:
            grad_wrt_input_vals = sess.run(
                grad_wrt_input,
                feed_dict=data_dict
            )[feature_layer_idx]

        importance = np.mean(grad_wrt_input_vals**2, axis=0, keepdims=True)

        return importance


    def _run_epoch(self, sess, dataset, pos_classes):
        """Run an epoch of training
        """
        batch_iterator = dataset.balanced_batches(
            pos_classes,
            batch_size=self.params.batch_size
        )

        X_holdout, y_holdout = dataset.get_holdout_samples()

        batch_counter = 0
        for X_batch, y_batch in batch_iterator:
            data_dict = {
                self.tf_mod.input: X_batch,
                self.tf_mod.target: y_batch,
                self.tf_mod.is_training: True
            }

            sess.run(
                self.tf_mod.train_step,
                feed_dict=data_dict
            )

            batch_counter += 1

            if batch_counter % 100 == 0:
                logging.info('Batch number %d', batch_counter)
                train_error = self.score(X_holdout, y_holdout)
                logging.info("Training score: %0.6f", train_error)

    def train(self, input_x, target_y, pos_classes):
        """
        Run a a bunch of training batches
        on the model using a bunch of input_x, target_y
        """

        dataset = DatasetManager(
            input_x, target_y,
            categorical=True, holdout_prop=0.1
        )

        try:
            with tf.Session(graph=self.tf_mod.graph) as sess:
                for epoch in range(self.params.num_epoch):
                    logging.info('Starting Epoch %d', epoch)
                    self._run_epoch(sess, dataset, pos_classes)
                    self.save(epoch)

        except KeyboardInterrupt:
            print('Force-exiting training.')
