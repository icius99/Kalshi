import unittest

from research.error_model import ForecastErrorModel


class ErrorModelTests(unittest.TestCase):
    def setUp(self):
        self.model = ForecastErrorModel(
            {
                "empirical_smoothing_alpha": 0.1,
                "buckets": {
                    "12": {
                        "n": 5,
                        "bias_f": 0.2,
                        "sd_error_f": 1.2,
                        "rmse_f": 1.3,
                        "error_counts": {"-1": 1, "0": 3, "1": 1},
                        "nbm_uncertainty_n": 5,
                        "nbm_uncertainty_scale": 1.25,
                    },
                    "24": {
                        "n": 5,
                        "bias_f": 0.4,
                        "sd_error_f": 2.0,
                        "rmse_f": 2.1,
                        "error_counts": {"-2": 1, "0": 2, "1": 1, "2": 1},
                        "nbm_uncertainty_n": 5,
                        "nbm_uncertainty_scale": 1.4,
                    },
                },
            }
        )

    def test_nearest(self):
        self.assertEqual(self.model.nearest(21).lead_hours, 24)

    def test_distance_guard(self):
        with self.assertRaises(ValueError):
            self.model.nearest(40, max_distance=8)

    def test_empirical_pmf_sums_to_one(self):
        fit = self.model.nearest(12)
        pmf = self.model.error_pmf(fit)
        self.assertAlmostEqual(sum(pmf.values()), 1.0, places=12)
        self.assertGreater(pmf[0], pmf[10])

    def test_market_probabilities_form_partition(self):
        markets = [
            {"market_ticker":"KXHIGHNY-26OCT04-T63","floor_strike":None,"cap_strike":63},
            {"market_ticker":"KXHIGHNY-26OCT04-B63.5","floor_strike":63,"cap_strike":64},
            {"market_ticker":"KXHIGHNY-26OCT04-B65.5","floor_strike":65,"cap_strike":66},
            {"market_ticker":"KXHIGHNY-26OCT04-B67.5","floor_strike":67,"cap_strike":68},
            {"market_ticker":"KXHIGHNY-26OCT04-B69.5","floor_strike":69,"cap_strike":70},
            {"market_ticker":"KXHIGHNY-26OCT04-T70","floor_strike":70,"cap_strike":None},
        ]
        fit, probabilities = self.model.probabilities_for_markets(
            markets, forecast_high_f=65, lead_hours=12, max_distance=2
        )
        self.assertEqual(fit.lead_hours, 12)
        self.assertAlmostEqual(sum(probabilities.values()), 1.0, places=12)
        # Historical bias is metadata; empirical probabilities come directly
        # from the residual counts rather than shifting the forecast by +0.2F.
        self.assertGreater(
            probabilities["KXHIGHNY-26OCT04-B65.5"],
            probabilities["KXHIGHNY-26OCT04-T70"],
        )

    def test_empirical_conditioning_removes_impossible_lower_outcomes(self):
        fit = self.model.nearest(12)
        pmf = self.model.conditioned_error_pmf(
            fit,
            forecast_high_f=65,
            minimum_actual_f=65,
        )
        self.assertAlmostEqual(sum(pmf.values()), 1.0, places=12)
        self.assertNotIn(-1, pmf)
        self.assertIn(0, pmf)
        self.assertIn(1, pmf)

    def test_scaled_uncertainty_probabilities_form_partition(self):
        markets = [
            {"market_ticker":"KXHIGHNY-26OCT04-T63","floor_strike":None,"cap_strike":63},
            {"market_ticker":"KXHIGHNY-26OCT04-B63.5","floor_strike":63,"cap_strike":64},
            {"market_ticker":"KXHIGHNY-26OCT04-B65.5","floor_strike":65,"cap_strike":66},
            {"market_ticker":"KXHIGHNY-26OCT04-B67.5","floor_strike":67,"cap_strike":68},
            {"market_ticker":"KXHIGHNY-26OCT04-B69.5","floor_strike":69,"cap_strike":70},
            {"market_ticker":"KXHIGHNY-26OCT04-T70","floor_strike":70,"cap_strike":None},
        ]
        fit, probabilities = self.model.probabilities_for_markets_scaled_uncertainty(
            markets,
            forecast_high_f=65,
            forecast_sigma_f=2,
            lead_hours=12,
            max_distance=2,
        )
        self.assertEqual(fit.lead_hours, 12)
        self.assertAlmostEqual(sum(probabilities.values()), 1.0, places=12)
        self.assertGreater(
            probabilities["KXHIGHNY-26OCT04-B65.5"],
            probabilities["KXHIGHNY-26OCT04-T70"],
        )

    def test_scaled_uncertainty_requires_fitted_scale(self):
        legacy = ForecastErrorModel(
            {
                "buckets": {
                    "12": {
                        "n": 1,
                        "bias_f": 0,
                        "sd_error_f": 1,
                        "rmse_f": 1,
                        "error_counts": {"0": 1},
                    }
                }
            }
        )
        with self.assertRaises(ValueError):
            legacy.probabilities_for_markets_scaled_uncertainty(
                [],
                forecast_high_f=65,
                forecast_sigma_f=2,
                lead_hours=12,
            )

    def test_forecast_definition_guard(self):
        compatible = ForecastErrorModel(
            {
                "forecast_definition": "calendar_day_nbm_txn_plus_early_tmp_v1",
                "buckets": {
                    "12": {
                        "n": 1,
                        "bias_f": 0,
                        "sd_error_f": 1,
                        "rmse_f": 1,
                        "error_counts": {"0": 1},
                    }
                },
            }
        )
        compatible.require_forecast_definition(
            "calendar_day_nbm_txn_plus_early_tmp_v1"
        )

        with self.assertRaises(ValueError):
            self.model.require_forecast_definition(
                "calendar_day_nbm_txn_plus_early_tmp_v1"
            )


if __name__ == "__main__":
    unittest.main()
