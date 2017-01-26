# -*- coding: utf-8 -*-
"""
Created on Sun Jan 15 00:03:22 2017

@author: jeffrey.gomberg
"""
import copy
from collections import defaultdict

import pandas as pd
import numpy as np

from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, \
    average_precision_score, brier_score_loss, fbeta_score, confusion_matrix

from creonmetrics import labeled_metric, assumed_metric, pu_score, pr_one_unlabeled, brier_score_partial_loss
from jeffsearchcv import JeffRandomSearchCV

def extract_scores_from_nested(scores):
    """ Extract scores from a sequence of dicts
    Returns a DataFrame where rows are CV, columns scores - use in conjuntion with NestedCV
    """
    row_dict = defaultdict(dict)
    for i, split_score_dict in enumerate(scores):
        d = {}
        for k, v in split_score_dict.items():
            if hasattr(v, "shape") and v.shape == (2, 2):
                tn, fp, fn, tp = v.ravel()
                d["tn_%s" % k] = tn
                d["fp_%s" % k] = fp
                d["fn_%s" % k] = fn
                d["tp_%s" % k] = tp
            if FrankenScorer.score_index != k:
                #don't include the "SCORE" score in the grid
                d[k] = v
        row_dict[i].update(d)

    score_grid = pd.DataFrame.from_dict(row_dict, orient="index")
    return score_grid


def extract_score_grid(searcher: JeffRandomSearchCV):
    """
    Take a fitted scorer that used a FrankenScorer() and extract the scoring data into a scoring grid

    The scorer must have cv_results_ as an attribute

    return: DataFrame of scores with means and std columns for each one as well when possible
        row is an iteration of a model, with columns of scores with splits with means, etc.

    TODO - finish this comment, error checking, and break up into fewer functions
    """
    results = pd.DataFrame(copy.deepcopy(searcher.cv_results_))
    splits = searcher.cv if searcher.cv is not None else 3
    rows = len(results)
    #create master_dict of scores
    master_dict = {}
    for row in range(rows):
        row_dict = defaultdict(dict)
        for split in range(splits):
            for tpe in ['test','train']:
                split_score_dict = copy.deepcopy(results['split{}_{}_score_data'.format(str(split), tpe)].iloc[row])
                d = {}
                for k, v in split_score_dict.items():
                    new_key = "{}_{}{}".format(k,tpe,split)
                    if hasattr(v, 'shape') and v.shape == (2, 2):
                        #confusion matric deconstruction
                        tn, fp, fn, tp = v.ravel()
                        d["tn_%s" % new_key] = tn
                        d["fp_%s" % new_key] = fp
                        d["fn_%s" % new_key] = fn
                        d["tp_%s" % new_key] = tp
                    if FrankenScorer.score_index != k:
                        #don't include the "SCORE" score in the grid
                        d[new_key] = v
                row_dict[row].update(d)
        master_dict.update(row_dict)

    score_grid = pd.DataFrame.from_dict(master_dict, orient="index")
    score_labels = set([s[:-1] for s in score_grid.columns])

    #compute mean and std
    for label in score_labels:
        label_score_grid = score_grid[[s for s in score_grid.columns if label == s[:-1]]]
        mean_for_label = label_score_grid.mean(axis=1)
        std_for_label = label_score_grid.std(axis=1)
        score_grid["mean_{}".format(label)] = mean_for_label
        score_grid["std_{}".format(label)] = std_for_label

    return score_grid

def get_mean_test_scores(score_grid):
    """ Return the "mean" and "test" columns of the score grid dataset
    """
    score_grid = score_grid.copy()
    return score_grid[[c for c in score_grid.columns if 'test' in c and 'mean' in c]]

class FrankenScorer():
    score_index = "SCORE"

    def __init__(self, decision_score='labeled_f1'):
        self.decision_score = decision_score

    """
    This is a sklearn scorer object that returns a (dictionary, Number) instead of a number
    """
    def __call__(self, estimator, X, y_true, sample_weight=None):
        y_pred = estimator.predict(X)
        y_prob = estimator.predict_proba(X)

        data = {'labeled_acc' : labeled_metric(y_true, y_pred, accuracy_score),
            'labeled_prec' : labeled_metric(y_true, y_pred, precision_score),
            'labeled_recall' : labeled_metric(y_true, y_pred, recall_score),
            'labeled_f1' : labeled_metric(y_true, y_pred, f1_score),
            'labeled_roc_auc' : labeled_metric(y_true, y_pred, roc_auc_score),
            'labeled_avg_prec' : labeled_metric(y_true, y_pred, average_precision_score),
            'labeled_brier' : labeled_metric(y_true, y_prob, brier_score_loss),
            'labeled_brier_pos' : labeled_metric(y_true, y_prob, brier_score_partial_loss, label=1),
            'labeled_brier_neg' : labeled_metric(y_true, y_prob, brier_score_partial_loss, label=0),
            'confusion_matrix_lab' : labeled_metric(y_true, y_pred, confusion_matrix),
            'pr_one_unlabeled' : pr_one_unlabeled(y_true, y_pred),
            'assumed_brier' : assumed_metric(y_true, y_prob, brier_score_loss),
            'assumed_brier_neg' : assumed_metric(y_true, y_prob, brier_score_partial_loss, label=0),
            'assumed_f1' : assumed_metric(y_true, y_pred, f1_score),
            'assumed_f1beta10' : assumed_metric(y_true, y_pred, fbeta_score, beta=10),
            'confusion_matrix_un' : assumed_metric(y_true, y_pred, confusion_matrix),
            'pu_score' : pu_score(y_true, y_pred),
            }

        ret = data[self.decision_score]
        data[self.score_index] = ret

        return data, ret

    def change_decision_score(self, decision_score):
        self.decision_score = decision_score
        return self


if __name__ == "__main__":
    #Just use this for testing
    from sklearn.datasets import load_breast_cancer
    from sklearn.ensemble import RandomForestClassifier

    X, y = load_breast_cancer(return_X_y=True)
    clf = RandomForestClassifier()
    import scipy as sp
    params = {'n_estimators': sp.stats.randint(low=10, high=500),
              'max_depth':[None, 1, 2, 3, 4, 5, 10, 20]}
    search = JeffRandomSearchCV(clf, params, scoring=FrankenScorer(), n_iter=2, verbose=100)
    search.fit(X, y)

    print(search.cv_results_)
