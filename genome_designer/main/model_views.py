"""
Classes that describe how a particular model should be viewed.
"""

from django.core.urlresolvers import reverse
from django.db.models.query import QuerySet

from main.constants import UNDEFINED_STRING
from main.models import Variant
from main.models import VariantCallerCommonData
from main.models import VariantAlternate
from main.models import VariantEvidence
from main.models import VariantSet
from scripts.dynamic_snp_filter_key_map import MAP_KEY__COMMON_DATA
from scripts.dynamic_snp_filter_key_map import MAP_KEY__ALTERNATE
from scripts.dynamic_snp_filter_key_map import MAP_KEY__EVIDENCE

class BaseVariantView(object):
    """Common methods for model views.
    """

    @classmethod
    def get_field_order(clazz, **kwargs):
        """Get the order of the models for displaying on the front-end.
        Called by the adapter.
        """
        if 'visible_key_names' in kwargs:
            variant_key_map = kwargs['variant_key_map']
            visible_key_names = kwargs['visible_key_names']

            additional_common_data_field_list = [field for field in
                    visible_key_names if field in
                    variant_key_map[MAP_KEY__COMMON_DATA]]

            additional_alternate_field_list = [field for field in
                    visible_key_names if field in
                    variant_key_map[MAP_KEY__ALTERNATE]]

            additional_evidence_field_list = [field for field in visible_key_names
                    if field in variant_key_map[MAP_KEY__EVIDENCE]]
        else:
            additional_common_data_field_list = []
            additional_evidence_field_list = []
            additional_alternate_field_list = []

        # Sort the visible keys into appropriate buckets based on the map.
        return (Variant.get_field_order() +
                VariantAlternate.get_field_order(
                        additional_field_list=additional_alternate_field_list) + 
                VariantCallerCommonData.get_field_order(
                        additional_field_list=additional_common_data_field_list) +
                VariantEvidence.get_field_order(
                        additional_field_list=additional_evidence_field_list))


class CastVariantView(BaseVariantView):
    """View of Variant that does not expose the individual
    VariantToExperimentSample relationships.
    """
    def __init__(self, variant):
        self.variant = variant
        self.variantalternate_list = (
                variant.variantalternate_set.all())
        self.variant_caller_common_data_list = (
                variant.variantcallercommondata_set.all())
        self.variant_evidence_list = VariantEvidence.objects.filter(
                variant_caller_common_data__variant=variant)

    def custom_getattr(self, attr):
        """For an attribute of a Variant, returns what you would expect.

        For many-to-one relations, e.g. VariantCallerCommonData and
        VariantEvidence, returns a '|'-separated list of values for
        that attribute.

        Returns:
            A string representing the view for the attribute.
        """
        delegate_order = [
                self.variant,
                self.variantalternate_list,
                self.variant_caller_common_data_list,
                self.variant_evidence_list
        ]
        for delegate in delegate_order:
            result_list = []

            # Convert to list for next step.
            if isinstance(delegate, QuerySet) or isinstance(delegate, list):
                delegate_list = delegate
            else:
                delegate_list = [delegate]

            # Iterate through the delegates.
            for delegate in delegate_list:

                if hasattr(delegate, attr):
                    result_list.append(getattr(delegate, attr))
                else:
                    try: result_list.append(delegate.as_dict()[attr])
                    except: pass

            # If no results, continue to next delegate.
            if not len(result_list):
                continue

            # If exactly one object, just return that object.
            if len(result_list) == 1:
                return result_list[0]

            # If 4 or less, return a '|'-separated string.
            # Number 4 is about how many short strings can reasonably fit in a
            # cell in the ui.
            # NOTE: This case is most useful for showing Variant ALTs.
            if len(result_list) <= 4:
                return ' | '.join([str(res) for res in result_list])

            # Otherwise return the count.
            return len(result_list)

        # Default.
        return UNDEFINED_STRING

    @classmethod
    def variant_as_cast_view(clazz, variant_obj,
            variant_id_to_metadata_dict=None):
        """Factory method returns a cast view for the given variant.

        Args:
            variant_obj: The Variant object to melt.
            variant_id_to_metadata_dict: See TODO.

        Returns:
            A CastVariantView instance.
        """
        # TODO: Do we need to modify the view based on passing samples in the
        # metadata.
        return CastVariantView(variant_obj)


class MeltedVariantView(BaseVariantView):
    """View of a Variant when showing one row per VariantToExperimentSample.
    """

    def __init__(self, variant, variant_caller_common_data=None,
            variant_evidence=None):
        self.variant = variant
        self.variantalternate_list = VariantAlternate.objects.filter(
                variant=variant, variantevidence=variant_evidence)
        self.variant_caller_common_data = variant_caller_common_data
        self.variant_evidence = variant_evidence

    def custom_getattr(self, attr):
        """Custom implementation of getting an attribute.

        We need this since to make sure we delegate to the objects that compose
        this object, in the correct order.
        """
        # Handle certain fields manually.
        # TODO: Come up with more generic way of manually handling fields.
        if attr == 'variantset_set':
            # TODO(gleb): Make the queries below efficient. Right now I'm just
            # trying to get it to work.
            variant_set_list = []
            if self.variant_evidence is None:
                # Return VariantSets which contain no ExperimentSample
                # association.
                no_sample_variant_sets = []
                for vtvs in self.variant.varianttovariantset_set.all():
                    if len(vtvs.sample_variant_set_association.all()) == 0:
                        no_sample_variant_sets.append(vtvs.variant_set)
                variant_set_list = no_sample_variant_sets

            else:
                # Only show sets associated with the VariantEvidence.
                sample = self.variant_evidence.experiment_sample
                variant_sets_for_this_sample = []
                for vtvs in self.variant.varianttovariantset_set.all():
                    if sample in vtvs.sample_variant_set_association.all():
                        variant_sets_for_this_sample.append(vtvs.variant_set)
                variant_set_list = variant_sets_for_this_sample
            # TODO: Return a QuerySet more efficiently. This is a temporary bug fix.
            variant_set_uid_list = [vs.uid for vs in variant_set_list]
            return VariantSet.objects.filter(uid__in=variant_set_uid_list)

        delegate_order = [
                self.variant,
                self.variantalternate_list,
                self.variant_caller_common_data,
                self.variant_evidence
        ]

        variant_caller_common_data_map = (
                self.variant.reference_genome.get_variant_caller_common_map())

        for delegate in delegate_order:
            result_list = []

            # Convert to list for next step.
            if isinstance(delegate, QuerySet):
                delegate_list = delegate
            else:
                delegate_list = [delegate]

            # Iterate through the delegates.
            for delegate in delegate_list:

                if hasattr(delegate, attr):
                    result_list.append(getattr(delegate, attr))
                else:
                    try:
                        result_list.append(delegate.as_dict()[attr])
                    except:
                        pass

            if len(result_list) == 1:
                # If one object, return it.
                return result_list[0]
            elif len(result_list) > 1:
                # Else if more than one, return a '|'-separated string.
                return ' | '.join([str(res) for res in result_list])

        return UNDEFINED_STRING

    @classmethod
    def variant_as_melted_list(clazz, variant_obj,
            variant_id_to_metadata_dict=None):
        """Factory method that melts the variant into a list of objects,
        one per common data per sample.

        Args:
            variant_obj: The Variant object to melt.
            variant_id_to_metadata_dict: Restrict melted entities to those
                related to these samples.

        Returns:
            List of MeltedVariantView objects corresponding to the Variant.
            This list will always be at least length 1.
        """
        melted_list = []

        all_common_data = variant_obj.variantcallercommondata_set.all()

        # We guarantee returning at least one row.
        if len(all_common_data) == 0:
            melted_list.append(MeltedVariantView(variant_obj, None, None))
            return melted_list

        # Otherwise iterate through
        for common_data_obj in all_common_data:
            # Return one row not associated with any sample.
            melted_list.append(MeltedVariantView(variant_obj, common_data_obj, None))

            variant_evidence_list = common_data_obj.variantevidence_set.all()
            if len(variant_evidence_list) == 0:
                continue

            if variant_id_to_metadata_dict is not None:
                passing_sample_ids = variant_id_to_metadata_dict[variant_obj.id].get(
                        'passing_sample_ids', set())
            else:
                passing_sample_ids = None

            for variant_evidence_obj in variant_evidence_list:
                if passing_sample_ids is not None:
                    # Don't add a row for VariantEvidence object if sample is
                    # not present.
                    sample_id = variant_evidence_obj.experiment_sample.id
                    if not sample_id in passing_sample_ids:
                        continue
                melted_list.append(MeltedVariantView(variant_obj, common_data_obj,
                        variant_evidence_obj))

        return melted_list


class GeneView(object):
    """View of a Gene.
    """

    def __init__(self, region):
        self.region = region
        self.label = region.label
        self.uid = region.uid

        # Assume that GENE region is composed of single interval.
        gene_interval = region.regioninterval_set.all()[0]
        self.start = gene_interval.start
        self.end = gene_interval.end

        # Count of Variants that occur in region.
        self.variants = Variant.objects.filter(
                reference_genome=region.reference_genome,
                position__gte=self.start,
                position__lt=self.end).count()

    @property
    def href(self):
        analyze_tab_part = reverse(
                'genome_designer.main.views.tab_root_analyze',
                args=(self.region.reference_genome.project.uid,
                        self.region.reference_genome.uid,
                        'variants'))
        gene_filter_part = '?filter=IN_GENE(' + self.label + ')'
        return analyze_tab_part + gene_filter_part


    @classmethod
    def get_field_order(clazz, **kwargs):
        return [
            {'field':'uid'},
            {'field':'label'},
            {'field':'start'},
            {'field':'end'},
            {'field':'variants'},
        ]
