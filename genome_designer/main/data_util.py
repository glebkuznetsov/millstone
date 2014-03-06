"""
Common methods for getting data from the backend.

These methods are intended to be used by both views.py, which should define
only pages, and xhr_handlers.py, which are intended to respond to AJAX
requests.

This module interacts closely with the ModelViews in model_views.py.
"""

from collections import defaultdict
from itertools import groupby

from django.db import connection

from main.model_views import CastVariantView
from main.model_views import MeltedVariantView
from main.models import ExperimentSample
from main.models import Variant
from main.models import VariantEvidence
from variants.common import dictfetchall
from variants.materialized_variant_filter import get_variants_that_pass_filter


class LookupVariantsResult(object):
    """Result of a call to lookup_variants.

    Attributes:
        result_list: List of cast or melted Variant objects.
        num_total_variants: Total number of variants that match query.
            For pagination.
    """
    def __init__(self, result_list, num_total_variants):
        self.result_list = result_list
        self.num_total_variants = num_total_variants


def lookup_variants(reference_genome, combined_filter_string, is_melted,
        pagination_start, pagination_len):
    """Manages the end-to-end flow of looking up Variants that match the
    given filter.

    This function delegates to the variant_filter module to get the list of
    variants matching the filter, and in cast or melted form depending on the
    is_melted flag.

    Returns:
        LookupVariantsResult object.
    """
    # Get the Variants that pass the filter.
    filter_eval_result = get_variants_that_pass_filter(combined_filter_string,
            reference_genome, is_melted)
    result_list = list(filter_eval_result.variant_set)

    page_results = result_list[pagination_start :
            pagination_start + pagination_len]
    print [result.obj_dict for result in page_results]

    if not is_melted:
        page_results = format_cast_objects(page_results)

    num_total_variants = len(page_results)

    return LookupVariantsResult(page_results, num_total_variants)


def format_cast_objects(page_results):
    for page_result in page_results:
        # Append ref with count of # variants without alt
        page_result['ref'] += ' (%d)' % page_result['alt'].count(None)

        # List frequency of each alt
        alts = filter(lambda alt: alt, page_result['alt'])
        alts.sort()
        page_result['alt'] = ' | '.join([
            '%s (%d)' % (val, len(list(group))) for val, group in groupby(alts)])

        # Add additional information specific to cast view
        page_result['variant_sets'] = ''
        page_result['total_samples'] = len(page_result['alt'])
    return page_results


def cast_joined_variant_objects(melted_variant_list):
    """Converts the list of melted variants into a cast representation.

    This means returning one row per variant, compressing columns
    into an aggregate representation. For example, in this initial
    implementation, the 'experiment_sample_uid' column becomes 'total_samples'.
    """
    cast_obj_list = []

    # First, we build a structure from variant id to list of result rows.
    variant_id_to_result_row = defaultdict(list)
    for result in melted_variant_list:
        variant_id_to_result_row[result['id']].append(result)

    for variant_id, result_row_list in variant_id_to_result_row.iteritems():
        assert len(result_row_list), "Not expected. Debug."
        position = result_row_list[0]['position']
        uid = result_row_list[0]['uid']

        # Count total samples.
        total_samples = 0
        all_sample_uids = set()
        for row in result_row_list:
            if row['experiment_sample_uid']:
                all_sample_uids.add(row['experiment_sample_uid'])
        total_samples = len(all_sample_uids)

        # Aggregate sets.
        variant_set_samples = defaultdict(set)
        for row in result_row_list:
            if row['variant_set_label']:
                variant_set_samples[row['variant_set_label']].add(
                        row['experiment_sample_uid'])
        variant_set_string_parts = []
        for label, sample_set in variant_set_samples.iteritems():
            none_null_samples = set()
            for sample in sample_set:
                if sample:
                    none_null_samples.add(sample)
            variant_set_string_parts.append(
                    label + ' (%d)' % len(none_null_samples))
        variant_set_string = ' | '.join(variant_set_string_parts)

        # Aggregate Variant alternates.
        total_alt_count = 0
        variant_alt_to_sample_dict = defaultdict(set)
        for row in result_row_list:
            if row['alt']:
                variant_alt_to_sample_dict[row['alt']].add(
                        row['experiment_sample_uid'])
        variant_alt_string_parts = []
        for alt, sample_set in variant_alt_to_sample_dict.iteritems():
            none_null_samples = set()
            for sample in sample_set:
                if sample:
                    none_null_samples.add(sample)
            variant_alt_string_parts.append(
                    alt + ' (%d)' % len(none_null_samples))
            total_alt_count += len(none_null_samples)
        variant_alt_string = ' | '.join(variant_alt_string_parts)

        # Now we can write the ref string.
        ref_string = result_row_list[0]['ref'] + ' (%d)' % (
                total_samples - total_alt_count)

        # Combine the aggregates into a single Cast object.
        cast_obj_list.append({
            'id': variant_id,
            'uid': uid,
            'position': position,
            'ref': ref_string,
            'alt': variant_alt_string,
            'total_samples': total_samples,
            'variant_sets': variant_set_string,
        })

    return cast_obj_list
