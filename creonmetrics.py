#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jan  3 07:41:57 2017

@author: jgomberg

This file will contain our custom scoring metrics
"""

from sklearn.metrics import brier_score_loss
from sklearn.metrics import make_scorer

def pu_score(y_true, y_pred):
   """
   Take truth vs predicted labels and calculate the pu-score, similar to f1-score.

   The formula for the PU score is::

       pu_score = recall ^ 2 / p(y_pred == 1)

   Assumption, label -1 == unlabeled, 0 == negative, 1 == positive
   """

   tp = sum([t == 1 and p == 1 for t, p in zip(y_true, y_pred)])
   n_pos = (y_true == 1).sum() if tp > 0 else 1
   recall = tp / n_pos

   pr_true = (y_pred == 1).sum() / len(y_pred)

   return recall * recall / pr_true

def prior_squared_error(y_true, y_pred, prior):
   """
   This will evaluate how many of the unlabeled data are pos_label and see as a percentage
   how far away it is from the prior

   Assumption: label -1 == unlabeled, 0 == negative, 1 == positive
   """

   unlabeled_pos = sum([t == -1 and p == 1 for t, p in zip(y_true, y_pred)])
   unlabeled_n = (y_true == -1).sum()

   if unlabeled_n == 0:
      #no unlabeleds, so no error
      return 0.0
   else:
      return ((unlabeled_pos / unlabeled_n) - prior) ** 2

def brier_score_labeled_loss(y_true, y_pred):
   """
   Calculate the brier score on only the labeled data in the set

   Assumption: label -1 == unlabeled, 0 == negative, 1 == positive
   """
   labeled_mask = y_true != -1
   return brier_score_loss(y_true = y_true[labeled_mask], y_prob = y_pred[labeled_mask])

# Scorers for model selection
pu_scorer = make_scorer(pu_score)
prior_squared_error_scorer_015 = make_scorer(prior_squared_error, greater_is_better=False, prior=0.015)
brier_score_labeled_loss_scorer = make_scorer(brier_score_labeled_loss, greater_is_better=False, needs_proba=True)