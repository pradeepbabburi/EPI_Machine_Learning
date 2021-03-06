#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 18 23:11:24 2017
"""

import warnings
from warnings import warn
import numpy as np
from scipy.sparse import issparse

from sklearn.externals.joblib import Parallel, delayed
from sklearn.utils.fixes import bincount
from sklearn.utils import check_random_state, check_array, compute_sample_weight
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree._tree import DTYPE, DOUBLE
from sklearn.exceptions import DataConversionWarning
from sklearn.utils.random import choice

__all__ = ["RandomForestSubsample"]

MAX_INT = np.iinfo(np.int32).max

def _generate_class_indices(y):
    return [np.where(y==c)[0] for c in np.unique(y)]

def _generate_sample_indices(random_state, y, target_imbalance_ratio, verbose=0):
    """Private function used to _parallel_build_trees function."""
    random_instance = check_random_state(random_state)

    class_idxs = _generate_class_indices(y)
    class_len = [len(class_idx) for class_idx in class_idxs]
    minority_class_idx = np.argmin(class_len)
    majority_class_idx = np.argmax(class_len)
    min_samples = class_len[minority_class_idx]
    maj_samples = int(min_samples / target_imbalance_ratio)
    n_samples = min_samples + maj_samples
    if verbose > 1:
        print("len(y):{} target_imbalance_ratio:{} minorities:{} majorities:{} "
              "n_samples:{}".format(len(y), target_imbalance_ratio, min_samples,
                         maj_samples, n_samples))

    maj_indices = choice(class_idxs[majority_class_idx], size=maj_samples, replace=False, random_state=random_instance)
    min_indices = class_idxs[minority_class_idx]
    indices_to_choose_from = np.hstack((min_indices, maj_indices))
    if verbose > 99:
        print("possible indicies to choose from: {}".format(indices_to_choose_from))

    sample_indices = choice(indices_to_choose_from, size=n_samples, replace=True, random_state=random_instance)
    if verbose > 99:
        print("chosen indicies: {}".format(sample_indices))

    return sample_indices

def _parallel_build_trees(tree, forest, X, y, sample_weight, tree_idx, n_trees,
                          verbose=0, class_weight=None, target_imbalance_ratio=None):
    """Private function used to fit a single tree in parallel."""
    if verbose > 1:
        print("building tree %d of %d" % (tree_idx + 1, n_trees))

    if forest.bootstrap:
        n_samples = X.shape[0]
        if sample_weight is None:
            curr_sample_weight = np.ones((n_samples,), dtype=np.float64)
        else:
            curr_sample_weight = sample_weight.copy()

        indices = _generate_sample_indices(tree.random_state, y,
                                           target_imbalance_ratio, verbose)
        sample_counts = bincount(indices, minlength=n_samples)
        curr_sample_weight *= sample_counts

        if class_weight == 'subsample':
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', DeprecationWarning)
                curr_sample_weight *= compute_sample_weight('auto', y, indices)
        elif class_weight == 'balanced_subsample':
            curr_sample_weight *= compute_sample_weight('balanced', y, indices)

        tree.fit(X, y, sample_weight=curr_sample_weight, check_input=False)
    else:
        tree.fit(X, y, sample_weight=sample_weight, check_input=False)

    return tree

class RandomForestSubsample(RandomForestClassifier):
    """ This is a random forest where every bootstrapped sample used for different trees in the forest is
    chosen from a subset of the data where a "target_imbalance_ratio" (number_minority_class / number_majority_class)
    Is between 0.1 and 1.0.  Once a more "balanced" subsample is chosen for a tree, a bootstrap of that population is
    then chosen to train that specific tree.
    """

    def __init__(self,
                 n_estimators=10,
                 criterion="gini",
                 max_depth=None,
                 min_samples_split=2,
                 min_samples_leaf=1,
                 min_weight_fraction_leaf=0.,
                 max_features="auto",
                 max_leaf_nodes=None,
                 min_impurity_split=1e-7,
                 bootstrap=True,
                 oob_score=False,
                 n_jobs=1,
                 random_state=None,
                 verbose=0,
                 warm_start=False,
                 class_weight=None,
                 target_imbalance_ratio=1.0):
        """ See RandomForestClassifier
        target_imbalance_ratio, optional, default = 1.0
            target ratio of minority class to majority class examples in each subsample
            Should be > 0.1 and <= 1.0
        """

        super(RandomForestSubsample, self).__init__(
                n_estimators=n_estimators,
                criterion=criterion,
                max_depth=max_depth,
                min_samples_split=min_samples_split,
                min_samples_leaf=min_samples_leaf,
                min_weight_fraction_leaf=min_weight_fraction_leaf,
                max_features=max_features,
                max_leaf_nodes=max_leaf_nodes,
                min_impurity_split=min_impurity_split,
                bootstrap=bootstrap,
                oob_score=oob_score,
                n_jobs=n_jobs,
                random_state=random_state,
                verbose=verbose,
                warm_start=warm_start,
                class_weight=class_weight)

        self.target_imbalance_ratio = target_imbalance_ratio


    def fit(self, X, y, sample_weight=None):
        """Build a forest of trees from the training set (X, y).

        Parameters
        ----------
        X : array-like or sparse matrix of shape = [n_samples, n_features]
            The training input samples. Internally, its dtype will be converted to
            ``dtype=np.float32``. If a sparse matrix is provided, it will be
            converted into a sparse ``csc_matrix``.

        y : array-like, shape = [n_samples] or [n_samples, n_outputs]
            The target values (class labels in classification, real numbers in
            regression).

        sample_weight : array-like, shape = [n_samples] or None
            Sample weights. If None, then samples are equally weighted. Splits
            that would create child nodes with net zero or negative weight are
            ignored while searching for a split in each node. In the case of
            classification, splits are also ignored if they would result in any
            single class carrying a negative weight in either child node.

        Returns
        -------
        self : object
            Returns self.
        """
        # Validate or convert input data
        X = check_array(X, accept_sparse="csc", dtype=DTYPE)
        y = check_array(y, accept_sparse='csc', ensure_2d=False, dtype=None)
        if issparse(X):
            # Pre-sort indices to avoid that each individual tree of the
            # ensemble sorts the indices.
            X.sort_indices()

        # Remap output
        n_samples, self.n_features_ = X.shape

        y = np.atleast_1d(y)
        if y.ndim == 2 and y.shape[1] == 1:
            warn("A column-vector y was passed when a 1d array was"
                 " expected. Please change the shape of y to "
                 "(n_samples,), for example using ravel().",
                 DataConversionWarning, stacklevel=2)

        if y.ndim == 1:
            # reshape is necessary to preserve the data contiguity against vs
            # [:, np.newaxis] that does not.
            y = np.reshape(y, (-1, 1))

        self.n_outputs_ = y.shape[1]

        y, expanded_class_weight = self._validate_y_class_weight(y)

        if getattr(y, "dtype", None) != DOUBLE or not y.flags.contiguous:
            y = np.ascontiguousarray(y, dtype=DOUBLE)

        if expanded_class_weight is not None:
            if sample_weight is not None:
                sample_weight = sample_weight * expanded_class_weight
            else:
                sample_weight = expanded_class_weight

        # Check parameters
        self._validate_estimator()

        if not self.bootstrap:
            raise ValueError("bootstrap=False is invalid for RandomForestSubsample")

        if not 0.1 < self.target_imbalance_ratio <= 1.0:
            raise ValueError("target_imbalance_ratio must be between 0.1 and 1.0")

        if not self.bootstrap and self.oob_score:
            raise ValueError("Out of bag estimation only available"
                             " if bootstrap=True")

        random_state = check_random_state(self.random_state)

        if not self.warm_start:
            # Free allocated memory, if any
            self.estimators_ = []

        n_more_estimators = self.n_estimators - len(self.estimators_)

        if n_more_estimators < 0:
            raise ValueError('n_estimators=%d must be larger or equal to '
                             'len(estimators_)=%d when warm_start==True'
                             % (self.n_estimators, len(self.estimators_)))

        elif n_more_estimators == 0:
            warn("Warm-start fitting without increasing n_estimators does not "
                 "fit new trees.")
        else:
            if self.warm_start and len(self.estimators_) > 0:
                # We draw from the random state to get the random state we
                # would have got if we hadn't used a warm_start.
                random_state.randint(MAX_INT, size=len(self.estimators_))

            trees = []
            for i in range(n_more_estimators):
                tree = self._make_estimator(append=False,
                                            random_state=random_state)
                trees.append(tree)

            # Parallel loop: we use the threading backend as the Cython code
            # for fitting the trees is internally releasing the Python GIL
            # making threading always more efficient than multiprocessing in
            # that case.
            trees = Parallel(n_jobs=self.n_jobs, verbose=self.verbose,
                             backend="threading")(
                delayed(_parallel_build_trees)(
                    t, self, X, y, sample_weight, i, len(trees),
                    verbose=self.verbose, class_weight=self.class_weight,
                    target_imbalance_ratio=self.target_imbalance_ratio)
                for i, t in enumerate(trees))

            # Collect newly grown trees
            self.estimators_.extend(trees)

        if self.oob_score:
            self._set_oob_score(X, y)

        # Decapsulate classes_ attributes
        if hasattr(self, "classes_") and self.n_outputs_ == 1:
            self.n_classes_ = self.n_classes_[0]
            self.classes_ = self.classes_[0]

        return self

if __name__ == "__main__":
    from sklearn.datasets import make_classification
    np.set_printoptions(threshold=np.nan)
    X, y = make_classification(n_samples=100, weights=[0.8, 0.2])
    sub = RandomForestSubsample(verbose=100)
    sub.fit(X, y)