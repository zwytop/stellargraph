#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2019 Data61, CSIRO
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

__all__ = ["UnsupervisedSampler"]


import random

from stellargraph.core.utils import is_real_iterable
from stellargraph.core.graph import StellarGraph
from stellargraph.data.explorer import UniformRandomWalk


class UnsupervisedSampler:
    """
        The UnsupervisedSampler is responsible for sampling walks in the given graph
        and returning positive and negative samples w.r.t. those walks, on demand.

        The positive samples are all the (target, context) pairs from the walks and the negative
        samples are contexts generated for each target based on a sampling distribtution.

        Currently only uniform random walks are performed, other walk strategies (such as
        second order walks) will be enabled in the future.

        Args:
            G (StellarGraph): A stellargraph with features.
            nodes (optional, iterable) The root nodes from which individual walks start.
                If not provided, all nodes in the graph are used.
            length (int): An integer giving the length of the walks. Length must be at least 2.
            number_of_walks (int): Number of walks from each root node.
    """

    def __init__(self, G, nodes=None, length=2, number_of_walks=1, seed=None):
        if not isinstance(G, StellarGraph):
            raise ValueError(
                "({}) Graph must be a StellarGraph or StellarDigraph object.".format(
                    type(self).__name__
                )
            )
        else:
            self.graph = G

        # Instantiate the walker class used to generate random walks in the graph
        self.walker = UniformRandomWalk(G, seed=seed)

        # This code will enable alternative walker classes
        # TODO: Enable this code, but figure out how to pass required options to run
        # if walker is not None:
        #     if not isinstance(
        #         walker, UniformRandomWalk
        #     ):  # only work with Uniform Random Walker at the moment
        #         raise TypeError(
        #             "({}) Only Uniform Random Walks are possible".format(
        #                 type(self).__name__
        #             )
        #         )
        #     else:
        #         self.walker = walker(G, seed=seed)
        # else:
        #         self.walker = UniformRandomWalk(G, seed=seed)

        # Define the root nodes for the walks
        # if no root nodes are provided for sampling defaulting to using all nodes as root nodes.
        if nodes is None:
            self.nodes = list(G.nodes())
        elif is_real_iterable(nodes):  # check whether the nodes provided are valid.
            self.nodes = list(nodes)
        else:
            raise ValueError("nodes parameter should be an iterableof node IDs.")

        # Require walks of at lease length two because to create a sample pair we need at least two nodes.
        if length < 2:
            raise ValueError(
                "({}) For generating (target,context) samples, walk length has to be at least 2".format(
                    type(self).__name__
                )
            )
        else:
            self.length = length

        if number_of_walks < 1:
            raise ValueError(
                "({}) At least 1 walk from each head node has to be done".format(
                    type(self).__name__
                )
            )
        else:
            self.number_of_walks = number_of_walks

        # Setup an interal random state with the given seed
        self.random = random.Random(seed)

    def run(self, batch_size):
        """
        This method returns a batch_size number of positive and negative samples from the graph.
        A random walk is generated from each root node, which are transformed into positive context
        pairs, and the same number of negative pairs are generated from a global node sampling
        distribution. The resulting list of context pairs are shuffled and converted to batches of
        size ``batch_size``.

        Currently the global node sampling distribution for the negative pairs is the degree
        distribution to the 3/4 power. This is the same used in node2vec
        (https://snap.stanford.edu/node2vec/).

        Args:
             batch_size (int): The number of samples to generate for each batch.
                This must be an even number.

        Returns:
            List of batches, where each batch is a tuple of (list context pairs, list of labels)
        """
        self._check_parameter_values(batch_size)

        all_nodes = list(self.graph.nodes())
        # Use the sampling distribution as per node2vec
        degrees = self.graph.node_degrees()
        sampling_distribution = [degrees[n] ** 0.75 for n in all_nodes]

        walks = self.walker.run(nodes=self.nodes, length=self.length, n=1, seed=0)

        # first item in each walk is the target/head node
        targets = [walk[0] for walk in walks]

        positive_pairs = [
            (target, positive_context)
            for target, walk in zip(targets, walks)
            for positive_context in walk[1:]
        ]

        negative_samples = self.random.choices(
            all_nodes, weights=sampling_distribution, k=len(positive_pairs)
        )
        negative_pairs = [
            (target, negative_context)
            for (target, _), negative_context in zip(positive_pairs, negative_samples)
        ]

        labels = [1] * len(positive_pairs) + [0] * len(negative_pairs)

        # zip and shuffle
        edge_ids_labels = list(zip(positive_pairs + negative_pairs, labels))
        self.random.shuffle(edge_ids_labels)

        # convert to batches
        return [
            tuple(zip(*edge_ids_labels[i : i + batch_size]))
            for i in range(0, len(edge_ids_labels), batch_size)
        ]

    def _check_parameter_values(self, batch_size):
        """
        Checks that the parameter values are valid or raises ValueError exceptions with a message indicating the
        parameter (the first one encountered in the checks) with invalid value.

        Args:
            batch_size: <int> number of samples to generate in each call of generator

        """

        if (
            batch_size is None
        ):  # must provide a batch size since this is an indicator of how many samples to return
            raise ValueError(
                "({}) The batch_size must be provided to generate samples for each batch in the epoch".format(
                    type(self).__name__
                )
            )

        if type(batch_size) != int:  # must be an integer
            raise TypeError(
                "({}) The batch_size must be positive integer.".format(
                    type(self).__name__
                )
            )

        if batch_size < 1:  # must be greater than 0
            raise ValueError(
                "({}) The batch_size must be positive integer.".format(
                    type(self).__name__
                )
            )

        if (
            batch_size % 2 != 0
        ):  # should be even since we generate 1 negative sample for each positive one.
            raise ValueError(
                "({}) The batch_size must be an even integer since equal number of positive and negative samples are generated in each batch.".format(
                    type(self).__name__
                )
            )
