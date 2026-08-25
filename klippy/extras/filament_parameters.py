import copy, os, logging

FILAMENT_LOAD_TEMP_UNKNOWN                      = 250
FILAMENT_UNLOAD_TEMP_UNKNOWN                    = 250
FILAMENT_CLEAN_NOZZLE_TEMP_UNKNOWN              = 170
FILAMENT_FLOW_TEMP_UNKNOWN                      = 220
FILAMENT_FLOW_K_UNKNOWN                         = 0.02
FILAMENT_FLOW_K_UNKNOWN_02                      = 0.20
FILAMENT_FLOW_K_UNKNOWN_04                      = 0.02
FILAMENT_FLOW_K_UNKNOWN_06                      = 0.012
FILAMENT_FLOW_K_UNKNOWN_08                      = 0.008
FILAMENT_FLOW_SLOW_V_UNKNOWN                    = 0.63
FILAMENT_FLOW_SLOW_V_UNKNOWN_02                 = 0.17
FILAMENT_FLOW_SLOW_V_UNKNOWN_04                 = 0.63
FILAMENT_FLOW_SLOW_V_UNKNOWN_06                 = 1.386
FILAMENT_FLOW_SLOW_V_UNKNOWN_08                 = 2.44
FILAMENT_FLOW_FAST_V_UNKNOWN                    = 4.99
FILAMENT_FLOW_FAST_V_UNKNOWN_02                 = 0.83
FILAMENT_FLOW_FAST_V_UNKNOWN_04                 = 4.99
FILAMENT_FLOW_FAST_V_UNKNOWN_06                 = 4.99
FILAMENT_FLOW_FAST_V_UNKNOWN_08                 = 4.99
FILAMENT_FLOW_ACCEL_UNKNOWN                     = 153.6
FILAMENT_FLOW_ACCEL_UNKNOWN_02                  = 40.5
FILAMENT_FLOW_ACCEL_UNKNOWN_04                  = 153.6
FILAMENT_FLOW_ACCEL_UNKNOWN_06                  = 339.6
FILAMENT_FLOW_ACCEL_UNKNOWN_08                  = 598.3
FILAMENT_FLOW_K_MIN_UNKNOWN                     = 0
FILAMENT_FLOW_K_MIN_UNKNOWN_02                  = 0
FILAMENT_FLOW_K_MIN_UNKNOWN_04                  = 0
FILAMENT_FLOW_K_MIN_UNKNOWN_06                  = 0
FILAMENT_FLOW_K_MIN_UNKNOWN_08                  = 0
FILAMENT_FLOW_K_MAX_UNKNOWN                     = 0.065
FILAMENT_FLOW_K_MAX_UNKNOWN_02                  = 0.300
FILAMENT_FLOW_K_MAX_UNKNOWN_04                  = 0.100
FILAMENT_FLOW_K_MAX_UNKNOWN_06                  = 0.070
FILAMENT_FLOW_K_MAX_UNKNOWN_08                  = 0.050

FILAMENT_IS_SOFT_UNKNOWN                        = False
FILAMENT_PARAMETER_VERSION                      = '1.0.0'

FORBIDDEN_FILAMENT_TYPES_02 = {
    'PLA': ['Wood'],
    'PLA-CF': ['*'],
    'PETG-CF': ['*'],
    'TPU': ['*'],
    'PVA': ['*'],
    'PA': ['*'],
    'PC': ['*'],
    'PEBA': ['*'],
    # any -CF filaments #
    # any -GF filaments #
}

FILAMENT_PARA_STANDARD_02_CFG_FILE              = 'filament_para_standard_02.json'
FILAMENT_PARA_STANDARD_04_CFG_FILE              = 'filament_para_standard_04.json'
FILAMENT_PARA_STANDARD_06_CFG_FILE              = 'filament_para_standard_06.json'
FILAMENT_PARA_STANDARD_08_CFG_FILE              = 'filament_para_standard_08.json'
FILAMENT_PARA_HIGH_FLOW_04_CFG_FILE             = 'filament_para_high_flow_04.json'

FILAMENT_PARA_CFG_STANDARD_02_DEFAULT = {
    # generic parameters
    'version': FILAMENT_PARAMETER_VERSION,
    'hard_filaments_max_flow_k': 0.40,
    'soft_filaments_max_flow_k': 0.60,
    'process_print_accel': 5000,
    'process_print_slow_v': 20,

    # PLA series
    'generic_PLA_generic_load_temp': 250,
    'generic_PLA_generic_unload_temp': 250,
    'generic_PLA_generic_is_soft': False,

    'generic_PLA_generic_print_temp': 220,
    'generic_PLA_generic_flow_k': 0.2,
    'generic_PLA_generic_flow_k_min': 0.01,
    'generic_PLA_generic_flow_k_max': 0.3,
    'generic_PLA_generic_vol_speed': 1.6,

    'Snapmaker_PLA_Basic_print_temp': 220,
    'Snapmaker_PLA_Basic_flow_k': 0.2,
    'Snapmaker_PLA_Basic_flow_k_min': 0.01,
    'Snapmaker_PLA_Basic_flow_k_max': 0.25,
    'Snapmaker_PLA_Basic_vol_speed': 2,

    'Snapmaker_PLA_SnapSpeed_print_temp': 220,
    'Snapmaker_PLA_SnapSpeed_flow_k': 0.2,
    'Snapmaker_PLA_SnapSpeed_flow_k_min': 0.01,
    'Snapmaker_PLA_SnapSpeed_flow_k_max': 0.25,
    'Snapmaker_PLA_SnapSpeed_vol_speed': 2,

    'Snapmaker_PLA_Matte_print_temp': 215,
    'Snapmaker_PLA_Matte_flow_k': 0.025,
    'Snapmaker_PLA_Matte_flow_k_min': 0.01,
    'Snapmaker_PLA_Matte_flow_k_max': 0.25,
    'Snapmaker_PLA_Matte_vol_speed': 2,

    'Snapmaker_PLA_Silk_print_temp': 230,
    'Snapmaker_PLA_Silk_flow_k': 0.015,
    'Snapmaker_PLA_Silk_flow_k_min': 0.01,
    'Snapmaker_PLA_Silk_flow_k_max': 0.25,
    'Snapmaker_PLA_Silk_vol_speed': 2,

    'Snapmaker_PLA_Translucent_print_temp': 220,
    'Snapmaker_PLA_Translucent_flow_k': 0.15,
    'Snapmaker_PLA_Translucent_flow_k_min': 0.01,
    'Snapmaker_PLA_Translucent_flow_k_max': 0.25,
    'Snapmaker_PLA_Translucent_vol_speed': 1.6,

    'Polymaker_PLA_PolyLite_print_temp': 220,
    'Polymaker_PLA_PolyLite_flow_k': 0.2,
    'Polymaker_PLA_PolyLite_flow_k_min': 0.01,
    'Polymaker_PLA_PolyLite_flow_k_max': 0.25,
    'Polymaker_PLA_PolyLite_vol_speed': 2,

    'Polymaker_PLA_PolySonic_print_temp': 220,
    'Polymaker_PLA_PolySonic_flow_k': 0.2,
    'Polymaker_PLA_PolySonic_flow_k_min': 0.01,
    'Polymaker_PLA_PolySonic_flow_k_max': 0.25,
    'Polymaker_PLA_PolySonic_vol_speed': 2,

    'Polymaker_PLA_PolyTerra_print_temp': 215,
    'Polymaker_PLA_PolyTerra_flow_k': 0.025,
    'Polymaker_PLA_PolyTerra_flow_k_min': 0.01,
    'Polymaker_PLA_PolyTerra_flow_k_max': 0.25,
    'Polymaker_PLA_PolyTerra_vol_speed': 2,

    # PETG series
    'generic_PETG_generic_load_temp': 270,
    'generic_PETG_generic_unload_temp': 270,
    'generic_PETG_generic_is_soft': False,

    'generic_PETG_generic_print_temp': 255,
    'generic_PETG_generic_flow_k': 0.25,
    'generic_PETG_generic_flow_k_min': 0.01,
    'generic_PETG_generic_flow_k_max': 0.3,
    'generic_PETG_generic_vol_speed': 1,

    'generic_PETG_HF_print_temp': 230,
    'generic_PETG_HF_flow_k': 0.04,
    'generic_PETG_HF_flow_k_min': 0.01,
    'generic_PETG_HF_flow_k_max': 0.3,
    'generic_PETG_HF_vol_speed': 2,

    'Snapmaker_PETG_generic_print_temp': 255,
    'Snapmaker_PETG_generic_flow_k': 0.25,
    'Snapmaker_PETG_generic_flow_k_min': 0.01,
    'Snapmaker_PETG_generic_flow_k_max': 0.3,
    'Snapmaker_PETG_generic_vol_speed': 2,

    'Snapmaker_PETG_HF_print_temp': 245,
    'Snapmaker_PETG_HF_flow_k': 0.02,
    'Snapmaker_PETG_HF_flow_k_min': 0.01,
    'Snapmaker_PETG_HF_flow_k_max': 0.3,
    'Snapmaker_PETG_HF_vol_speed': 2,

    'Snapmaker_PETG_Translucent_print_temp': 245,
    'Snapmaker_PETG_Translucent_flow_k': 0.23,
    'Snapmaker_PETG_Translucent_flow_k_min': 0.01,
    'Snapmaker_PETG_Translucent_flow_k_max': 0.3,
    'Snapmaker_PETG_Translucent_vol_speed': 1,

    'Polymaker_PETG_PolyLite_print_temp': 255,
    'Polymaker_PETG_PolyLite_flow_k': 0.25,
    'Polymaker_PETG_PolyLite_flow_k_min': 0.01,
    'Polymaker_PETG_PolyLite_flow_k_max': 0.3,
    'Polymaker_PETG_PolyLite_vol_speed': 1,

    # ABS series
    'generic_ABS_generic_load_temp': 280,
    'generic_ABS_generic_unload_temp': 280,
    'generic_ABS_generic_is_soft': False,

    'generic_ABS_generic_print_temp': 270,
    'generic_ABS_generic_flow_k': 0.2,
    'generic_ABS_generic_flow_k_min': 0.01,
    'generic_ABS_generic_flow_k_max': 0.3,
    'generic_ABS_generic_vol_speed': 2,

    'Snapmaker_ABS_generic_print_temp': 270,
    'Snapmaker_ABS_generic_flow_k': 0.1,
    'Snapmaker_ABS_generic_flow_k_min': 0.03,
    'Snapmaker_ABS_generic_flow_k_max': 0.3,
    'Snapmaker_ABS_generic_vol_speed': 2,

    'Polymaker_ABS_PolyLite_print_temp': 270,
    'Polymaker_ABS_PolyLite_flow_k': 0.1,
    'Polymaker_ABS_PolyLite_flow_k_min': 0.03,
    'Polymaker_ABS_PolyLite_flow_k_max': 0.3,
    'Polymaker_ABS_PolyLite_vol_speed': 2,

    # ASA series
    'generic_ASA_generic_load_temp': 280,
    'generic_ASA_generic_unload_temp': 280,
    'generic_ASA_generic_is_soft': False,

    'generic_ASA_generic_print_temp': 260,
    'generic_ASA_generic_flow_k': 0.2,
    'generic_ASA_generic_flow_k_min': 0.03,
    'generic_ASA_generic_flow_k_max': 0.3,
    'generic_ASA_generic_vol_speed': 2,

    'Snapmaker_ASA_generic_print_temp': 270,
    'Snapmaker_ASA_generic_flow_k': 0.15,
    'Snapmaker_ASA_generic_flow_k_min': 0.03,
    'Snapmaker_ASA_generic_flow_k_max': 0.3,
    'Snapmaker_ASA_generic_vol_speed': 2,
}

FILAMENT_PARA_CFG_STANDARD_04_DEFAULT = {
    # generic parameters
    'version': FILAMENT_PARAMETER_VERSION,
    'hard_filaments_max_flow_k': 0.40,
    'soft_filaments_max_flow_k': 0.60,
    'process_print_accel': 5000,
    'process_print_slow_v': 20,

    # PLA series
    'generic_PLA_generic_load_temp': 250,
    'generic_PLA_generic_unload_temp': 250,
    'generic_PLA_generic_is_soft': False,

    'generic_PLA_generic_print_temp': 220,
    'generic_PLA_generic_flow_k': 0.02,
    'generic_PLA_generic_flow_k_min': 0.005,
    'generic_PLA_generic_flow_k_max': 0.065,
    'generic_PLA_generic_vol_speed': 12,

    'Snapmaker_PLA_Basic_print_temp': 220,
    'Snapmaker_PLA_Basic_flow_k': 0.02,
    'Snapmaker_PLA_Basic_flow_k_min': 0.005,
    'Snapmaker_PLA_Basic_flow_k_max': 0.040,
    'Snapmaker_PLA_Basic_vol_speed': 15,

    'Snapmaker_PLA_SnapSpeed_print_temp': 220,
    'Snapmaker_PLA_SnapSpeed_flow_k': 0.02,
    'Snapmaker_PLA_SnapSpeed_flow_k_min': 0.005,
    'Snapmaker_PLA_SnapSpeed_flow_k_max': 0.040,
    'Snapmaker_PLA_SnapSpeed_vol_speed': 20,

    'Snapmaker_PLA_Matte_print_temp': 215,
    'Snapmaker_PLA_Matte_flow_k': 0.02,
    'Snapmaker_PLA_Matte_flow_k_min': 0.005,
    'Snapmaker_PLA_Matte_flow_k_max': 0.040,
    'Snapmaker_PLA_Matte_vol_speed': 22,

    'Snapmaker_PLA_Silk_print_temp': 230,
    'Snapmaker_PLA_Silk_flow_k': 0.015,
    'Snapmaker_PLA_Silk_flow_k_min': 0.005,
    'Snapmaker_PLA_Silk_flow_k_max': 0.040,
    'Snapmaker_PLA_Silk_vol_speed': 10,

    'Snapmaker_PLA_Wood_print_temp': 220,
    'Snapmaker_PLA_Wood_flow_k': 0.025,
    'Snapmaker_PLA_Wood_flow_k_min': 0.005,
    'Snapmaker_PLA_Wood_flow_k_max': 0.040,
    'Snapmaker_PLA_Wood_vol_speed': 18,

    'Snapmaker_PLA_Full Spectrum_print_temp': 220,
    'Snapmaker_PLA_Full Spectrum_flow_k': 0.02,
    'Snapmaker_PLA_Full Spectrum_flow_k_min': 0.005,
    'Snapmaker_PLA_Full Spectrum_flow_k_max': 0.040,
    'Snapmaker_PLA_Full Spectrum_vol_speed': 15,

    'Snapmaker_PLA_Translucent_print_temp': 220,
    'Snapmaker_PLA_Translucent_flow_k': 0.02,
    'Snapmaker_PLA_Translucent_flow_k_min': 0.005,
    'Snapmaker_PLA_Translucent_flow_k_max': 0.040,
    'Snapmaker_PLA_Translucent_vol_speed': 12,

    'Polymaker_PLA_PolyLite_print_temp': 220,
    'Polymaker_PLA_PolyLite_flow_k': 0.02,
    'Polymaker_PLA_PolyLite_flow_k_min': 0.005,
    'Polymaker_PLA_PolyLite_flow_k_max': 0.040,
    'Polymaker_PLA_PolyLite_vol_speed': 15,

    'Polymaker_PLA_PolySonic_print_temp': 220,
    'Polymaker_PLA_PolySonic_flow_k': 0.02,
    'Polymaker_PLA_PolySonic_flow_k_min': 0.005,
    'Polymaker_PLA_PolySonic_flow_k_max': 0.040,
    'Polymaker_PLA_PolySonic_vol_speed': 20,

    'Polymaker_PLA_PolyTerra_print_temp': 215,
    'Polymaker_PLA_PolyTerra_flow_k': 0.02,
    'Polymaker_PLA_PolyTerra_flow_k_min': 0.005,
    'Polymaker_PLA_PolyTerra_flow_k_max': 0.040,
    'Polymaker_PLA_PolyTerra_vol_speed': 22,

    # PLA-CF series
    'generic_PLA-CF_generic_load_temp': 250,
    'generic_PLA-CF_generic_unload_temp': 250,
    'generic_PLA-CF_generic_is_soft': False,

    'generic_PLA-CF_generic_print_temp': 220,
    'generic_PLA-CF_generic_flow_k': 0.02,
    'generic_PLA-CF_generic_flow_k_min': 0.005,
    'generic_PLA-CF_generic_flow_k_max': 0.065,
    'generic_PLA-CF_generic_vol_speed': 12,

    'Snapmaker_PLA-CF_generic_print_temp': 240,
    'Snapmaker_PLA-CF_generic_flow_k': 0.01,
    'Snapmaker_PLA-CF_generic_flow_k_min': 0.005,
    'Snapmaker_PLA-CF_generic_flow_k_max': 0.035,
    'Snapmaker_PLA-CF_generic_vol_speed': 15,

    # PETG series
    'generic_PETG_generic_load_temp': 270,
    'generic_PETG_generic_unload_temp': 270,
    'generic_PETG_generic_is_soft': False,

    'generic_PETG_generic_print_temp': 255,
    'generic_PETG_generic_flow_k': 0.04,
    'generic_PETG_generic_flow_k_min': 0.005,
    'generic_PETG_generic_flow_k_max': 0.065,
    'generic_PETG_generic_vol_speed': 12,

    'generic_PETG_HF_print_temp': 230,
    'generic_PETG_HF_flow_k': 0.04,
    'generic_PETG_HF_flow_k_min': 0.005,
    'generic_PETG_HF_flow_k_max': 0.065,
    'generic_PETG_HF_vol_speed': 16,

    'Snapmaker_PETG_generic_print_temp': 255,
    'Snapmaker_PETG_generic_flow_k': 0.05,
    'Snapmaker_PETG_generic_flow_k_min': 0.02,
    'Snapmaker_PETG_generic_flow_k_max': 0.065,
    'Snapmaker_PETG_generic_vol_speed': 12,

    'Snapmaker_PETG_HF_print_temp': 245,
    'Snapmaker_PETG_HF_flow_k': 0.02,
    'Snapmaker_PETG_HF_flow_k_min': 0.005,
    'Snapmaker_PETG_HF_flow_k_max': 0.040,
    'Snapmaker_PETG_HF_vol_speed': 20,

    'Snapmaker_PETG_Translucent_print_temp': 250,
    'Snapmaker_PETG_Translucent_flow_k': 0.04,
    'Snapmaker_PETG_Translucent_flow_k_min': 0.02,
    'Snapmaker_PETG_Translucent_flow_k_max': 0.06,
    'Snapmaker_PETG_Translucent_vol_speed': 10,

    'Polymaker_PETG_PolyLite_print_temp': 255,
    'Polymaker_PETG_PolyLite_flow_k': 0.04,
    'Polymaker_PETG_PolyLite_flow_k_min': 0.005,
    'Polymaker_PETG_PolyLite_flow_k_max': 0.065,
    'Polymaker_PETG_PolyLite_vol_speed': 12,

    # PETG-CF series
    'generic_PETG-CF_generic_load_temp': 270,
    'generic_PETG-CF_generic_unload_temp': 270,
    'generic_PETG-CF_generic_is_soft': False,

    'generic_PETG-CF_generic_print_temp': 255,
    'generic_PETG-CF_generic_flow_k': 0.02,
    'generic_PETG-CF_generic_flow_k_min': 0.005,
    'generic_PETG-CF_generic_flow_k_max': 0.065,
    'generic_PETG-CF_generic_vol_speed': 11,

    'Snapmaker_PETG-CF_generic_print_temp': 255,
    'Snapmaker_PETG-CF_generic_flow_k': 0.02,
    'Snapmaker_PETG-CF_generic_flow_k_min': 0.005,
    'Snapmaker_PETG-CF_generic_flow_k_max': 0.040,
    'Snapmaker_PETG-CF_generic_vol_speed': 12,

    # ABS series
    'generic_ABS_generic_load_temp': 280,
    'generic_ABS_generic_unload_temp': 280,
    'generic_ABS_generic_is_soft': False,

    'generic_ABS_generic_print_temp': 270,
    'generic_ABS_generic_flow_k': 0.02,
    'generic_ABS_generic_flow_k_min': 0.005,
    'generic_ABS_generic_flow_k_max': 0.065,
    'generic_ABS_generic_vol_speed': 15,

    'Snapmaker_ABS_generic_print_temp': 265,
    'Snapmaker_ABS_generic_flow_k': 0.02,
    'Snapmaker_ABS_generic_flow_k_min': 0.005,
    'Snapmaker_ABS_generic_flow_k_max': 0.035,
    'Snapmaker_ABS_generic_vol_speed': 15,

    'Polymaker_ABS_PolyLite_print_temp': 265,
    'Polymaker_ABS_PolyLite_flow_k': 0.02,
    'Polymaker_ABS_PolyLite_flow_k_min': 0.005,
    'Polymaker_ABS_PolyLite_flow_k_max': 0.035,
    'Polymaker_ABS_PolyLite_vol_speed': 15,

    # ASA series
    'generic_ASA_generic_load_temp': 280,
    'generic_ASA_generic_unload_temp': 280,
    'generic_ASA_generic_is_soft': False,

    'generic_ASA_generic_print_temp': 260,
    'generic_ASA_generic_flow_k': 0.02,
    'generic_ASA_generic_flow_k_min': 0.005,
    'generic_ASA_generic_flow_k_max': 0.065,
    'generic_ASA_generic_vol_speed': 12,

    'Snapmaker_ASA_generic_print_temp': 270,
    'Snapmaker_ASA_generic_flow_k': 0.02,
    'Snapmaker_ASA_generic_flow_k_min': 0.005,
    'Snapmaker_ASA_generic_flow_k_max': 0.035,
    'Snapmaker_ASA_generic_vol_speed': 15,

    # TPU series
    'generic_TPU_generic_load_temp': 250,
    'generic_TPU_generic_unload_temp': 250,
    'generic_TPU_generic_is_soft': True,
    'generic_TPU_generic_print_temp': 240,
    'generic_TPU_generic_flow_k': 0.4,
    'generic_TPU_generic_flow_k_min': 0.15,
    'generic_TPU_generic_flow_k_max': 0.45,
    'generic_TPU_generic_vol_speed': 3.2,

    'generic_TPU_90A_load_temp': 250,
    'generic_TPU_90A_unload_temp': 250,
    'generic_TPU_90A_is_soft': True,
    'generic_TPU_90A_print_temp': 230,
    'generic_TPU_90A_flow_k': 0.4,
    'generic_TPU_90A_flow_k_min': 0.15,
    'generic_TPU_90A_flow_k_max': 0.45,
    'generic_TPU_90A_vol_speed': 3.2,

    'generic_TPU_95A HF_load_temp': 250,
    'generic_TPU_95A HF_unload_temp': 250,
    'generic_TPU_95A HF_is_soft': True,
    'generic_TPU_95A HF_print_temp': 235,
    'generic_TPU_95A HF_flow_k': 0.15,
    'generic_TPU_95A HF_flow_k_min': 0.05,
    'generic_TPU_95A HF_flow_k_max': 0.25,
    'generic_TPU_95A HF_vol_speed': 10.5,

    'Snapmaker_TPU_90A_print_temp': 230,
    'Snapmaker_TPU_90A_flow_k': 0.4,
    'Snapmaker_TPU_90A_flow_k_min': 0.15,
    'Snapmaker_TPU_90A_flow_k_max': 0.45,
    'Snapmaker_TPU_90A_vol_speed': 3.2,

    'Snapmaker_TPU_95A HF_print_temp': 230,
    'Snapmaker_TPU_95A HF_flow_k': 0.23,
    'Snapmaker_TPU_95A HF_flow_k_min': 0.15,
    'Snapmaker_TPU_95A HF_flow_k_max': 0.36,
    'Snapmaker_TPU_95A HF_vol_speed': 9.0,

    # PA series
    'generic_PA_generic_load_temp': 280,
    'generic_PA_generic_unload_temp': 280,
    'generic_PA_generic_is_soft': False,

    'generic_PA_generic_print_temp': 260,
    'generic_PA_generic_flow_k': 0.02,
    'generic_PA_generic_flow_k_min': 0.005,
    'generic_PA_generic_flow_k_max': 0.065,
    'generic_PA_generic_vol_speed': 12,

    # PA-CF series
    'generic_PA-CF_generic_load_temp': 300,
    'generic_PA-CF_generic_unload_temp': 300,
    'generic_PA-CF_generic_is_soft': False,
    'generic_PA-CF_generic_print_temp': 290,
    'generic_PA-CF_generic_flow_k': 0.02,
    'generic_PA-CF_generic_flow_k_min': 0.005,
    'generic_PA-CF_generic_flow_k_max': 0.065,
    'generic_PA-CF_generic_vol_speed': 8,

    # PA6-CF series
    'generic_PA6-CF_generic_load_temp': 290,
    'generic_PA6-CF_generic_unload_temp': 290,
    'generic_PA6-CF_generic_is_soft': False,
    'generic_PA6-CF_generic_print_temp': 275,
    'generic_PA6-CF_generic_flow_k': 0.02,
    'generic_PA6-CF_generic_flow_k_min': 0.005,
    'generic_PA6-CF_generic_flow_k_max': 0.065,
    'generic_PA6-CF_generic_vol_speed': 8,

    # PA-GF series
    'generic_PA-GF_generic_load_temp': 300,
    'generic_PA-GF_generic_unload_temp': 300,
    'generic_PA-GF_generic_is_soft': False,
    'generic_PA-GF_generic_print_temp': 290,
    'generic_PA-GF_generic_flow_k': 0.02,
    'generic_PA-GF_generic_flow_k_min': 0.005,
    'generic_PA-GF_generic_flow_k_max': 0.065,
    'generic_PA-GF_generic_vol_speed': 8,

    # PA6-GF series
    'generic_PA6-GF_generic_load_temp': 280,
    'generic_PA6-GF_generic_unload_temp': 280,
    'generic_PA6-GF_generic_is_soft': False,
    'generic_PA6-GF_generic_print_temp': 265,
    'generic_PA6-GF_generic_flow_k': 0.02,
    'generic_PA6-GF_generic_flow_k_min': 0.005,
    'generic_PA6-GF_generic_flow_k_max': 0.065,
    'generic_PA6-GF_generic_vol_speed': 10.5,

    # PC series
    'generic_PC_generic_load_temp': 300,
    'generic_PC_generic_unload_temp': 300,
    'generic_PC_generic_is_soft': False,
    'generic_PC_generic_print_temp': 280,
    'generic_PC_generic_flow_k': 0.02,
    'generic_PC_generic_flow_k_min': 0.005,
    'generic_PC_generic_flow_k_max': 0.065,
    'generic_PC_generic_vol_speed': 16,

    # PC-ABS series
    'generic_PC-ABS_generic_load_temp': 300,
    'generic_PC-ABS_generic_unload_temp': 300,
    'generic_PC-ABS_generic_is_soft': False,
    'generic_PC-ABS_generic_print_temp': 280,
    'generic_PC-ABS_generic_flow_k': 0.02,
    'generic_PC-ABS_generic_flow_k_min': 0.005,
    'generic_PC-ABS_generic_flow_k_max': 0.065,
    'generic_PC-ABS_generic_vol_speed': 16,

    # PVA series
    'generic_PVA_generic_load_temp': 250,
    'generic_PVA_generic_unload_temp': 250,
    'generic_PVA_generic_is_soft': True,
    'generic_PVA_generic_print_temp': 240,
    'generic_PVA_generic_flow_k': 0.028,
    'generic_PVA_generic_flow_k_min': 0.01,
    'generic_PVA_generic_flow_k_max': 0.065,
    'generic_PVA_generic_vol_speed': 6,

    # PEBA series
    'generic_PEBA_generic_load_temp': 250,
    'generic_PEBA_generic_unload_temp': 250,
    'generic_PEBA_generic_is_soft': True,

    'generic_PEBA_generic_print_temp': 235,
    'generic_PEBA_generic_flow_k': 0.4,
    'generic_PEBA_generic_flow_k_min': 0.15,
    'generic_PEBA_generic_flow_k_max': 0.45,
    'generic_PEBA_generic_vol_speed': 5,

    'Snapmaker_PEBA_90A_print_temp': 235,
    'Snapmaker_PEBA_90A_flow_k': 0.4,
    'Snapmaker_PEBA_90A_flow_k_min': 0.15,
    'Snapmaker_PEBA_90A_flow_k_max': 0.45,
    'Snapmaker_PEBA_90A_vol_speed': 5,
}

FILAMENT_PARA_CFG_STANDARD_06_DEFAULT = {
    # generic parameters
    'version': FILAMENT_PARAMETER_VERSION,
    'hard_filaments_max_flow_k': 0.40,
    'soft_filaments_max_flow_k': 0.60,
    'process_print_accel': 5000,
    'process_print_slow_v': 20,

    # PLA series
    'generic_PLA_generic_load_temp': 250,
    'generic_PLA_generic_unload_temp': 250,
    'generic_PLA_generic_is_soft': False,

    'generic_PLA_generic_print_temp': 220,
    'generic_PLA_generic_flow_k': 0.012,
    'generic_PLA_generic_flow_k_min': 0.001,
    'generic_PLA_generic_flow_k_max': 0.03,
    'generic_PLA_generic_vol_speed': 12,

    'Snapmaker_PLA_Basic_print_temp': 220,
    'Snapmaker_PLA_Basic_flow_k': 0.012,
    'Snapmaker_PLA_Basic_flow_k_min': 0.005,
    'Snapmaker_PLA_Basic_flow_k_max': 0.025,
    'Snapmaker_PLA_Basic_vol_speed': 15,

    'Snapmaker_PLA_SnapSpeed_print_temp': 220,
    'Snapmaker_PLA_SnapSpeed_flow_k': 0.02,
    'Snapmaker_PLA_SnapSpeed_flow_k_min': 0.005,
    'Snapmaker_PLA_SnapSpeed_flow_k_max': 0.025,
    'Snapmaker_PLA_SnapSpeed_vol_speed': 20,

    'Snapmaker_PLA_Matte_print_temp': 215,
    'Snapmaker_PLA_Matte_flow_k': 0.015,
    'Snapmaker_PLA_Matte_flow_k_min': 0.005,
    'Snapmaker_PLA_Matte_flow_k_max': 0.025,
    'Snapmaker_PLA_Matte_vol_speed': 20,

    'Snapmaker_PLA_Silk_print_temp': 230,
    'Snapmaker_PLA_Silk_flow_k': 0.015,
    'Snapmaker_PLA_Silk_flow_k_min': 0.005,
    'Snapmaker_PLA_Silk_flow_k_max': 0.025,
    'Snapmaker_PLA_Silk_vol_speed': 10,

    'Snapmaker_PLA_Wood_print_temp': 220,
    'Snapmaker_PLA_Wood_flow_k': 0.014,
    'Snapmaker_PLA_Wood_flow_k_min': 0.005,
    'Snapmaker_PLA_Wood_flow_k_max': 0.025,
    'Snapmaker_PLA_Wood_vol_speed': 18,

    'Snapmaker_PLA_Translucent_print_temp': 220,
    'Snapmaker_PLA_Translucent_flow_k': 0.02,
    'Snapmaker_PLA_Translucent_flow_k_min': 0.005,
    'Snapmaker_PLA_Translucent_flow_k_max': 0.025,
    'Snapmaker_PLA_Translucent_vol_speed': 12,

    'Polymaker_PLA_PolyLite_print_temp': 220,
    'Polymaker_PLA_PolyLite_flow_k': 0.012,
    'Polymaker_PLA_PolyLite_flow_k_min': 0.005,
    'Polymaker_PLA_PolyLite_flow_k_max': 0.025,
    'Polymaker_PLA_PolyLite_vol_speed': 15,

    'Polymaker_PLA_PolySonic_print_temp': 220,
    'Polymaker_PLA_PolySonic_flow_k': 0.02,
    'Polymaker_PLA_PolySonic_flow_k_min': 0.005,
    'Polymaker_PLA_PolySonic_flow_k_max': 0.025,
    'Polymaker_PLA_PolySonic_vol_speed': 20,

    'Polymaker_PLA_PolyTerra_print_temp': 215,
    'Polymaker_PLA_PolyTerra_flow_k': 0.015,
    'Polymaker_PLA_PolyTerra_flow_k_min': 0.005,
    'Polymaker_PLA_PolyTerra_flow_k_max': 0.025,
    'Polymaker_PLA_PolyTerra_vol_speed': 20,

    # PLA-CF series
    'generic_PLA-CF_generic_load_temp': 250,
    'generic_PLA-CF_generic_unload_temp': 250,
    'generic_PLA-CF_generic_is_soft': False,

    'generic_PLA-CF_generic_print_temp': 220,
    'generic_PLA-CF_generic_flow_k': 0.012,
    'generic_PLA-CF_generic_flow_k_min': 0.001,
    'generic_PLA-CF_generic_flow_k_max': 0.03,
    'generic_PLA-CF_generic_vol_speed': 12,

    'Snapmaker_PLA-CF_generic_print_temp': 220,
    'Snapmaker_PLA-CF_generic_flow_k': 0.015,
    'Snapmaker_PLA-CF_generic_flow_k_min': 0.005,
    'Snapmaker_PLA-CF_generic_flow_k_max': 0.025,
    'Snapmaker_PLA-CF_generic_vol_speed': 18,

    # PETG series
    'generic_PETG_generic_load_temp': 270,
    'generic_PETG_generic_unload_temp': 270,
    'generic_PETG_generic_is_soft': False,

    'generic_PETG_generic_print_temp': 255,
    'generic_PETG_generic_flow_k': 0.015,
    'generic_PETG_generic_flow_k_min': 0.005,
    'generic_PETG_generic_flow_k_max': 0.045,
    'generic_PETG_generic_vol_speed': 12,

    'generic_PETG_HF_print_temp': 230,
    'generic_PETG_HF_flow_k': 0.012,
    'generic_PETG_HF_flow_k_min': 0.005,
    'generic_PETG_HF_flow_k_max': 0.045,
    'generic_PETG_HF_vol_speed': 16,

    'Snapmaker_PETG_generic_print_temp': 255,
    'Snapmaker_PETG_generic_flow_k': 0.03,
    'Snapmaker_PETG_generic_flow_k_min': 0.010,
    'Snapmaker_PETG_generic_flow_k_max': 0.045,
    'Snapmaker_PETG_generic_vol_speed': 12,

    'Snapmaker_PETG_HF_print_temp': 245,
    'Snapmaker_PETG_HF_flow_k': 0.02,
    'Snapmaker_PETG_HF_flow_k_min': 0.005,
    'Snapmaker_PETG_HF_flow_k_max': 0.030,
    'Snapmaker_PETG_HF_vol_speed': 20,

    'Snapmaker_PETG_Translucent_print_temp': 245,
    'Snapmaker_PETG_Translucent_flow_k': 0.02,
    'Snapmaker_PETG_Translucent_flow_k_min': 0.01,
    'Snapmaker_PETG_Translucent_flow_k_max': 0.04,
    'Snapmaker_PETG_Translucent_vol_speed': 16,

    'Polymaker_PETG_PolyLite_print_temp': 255,
    'Polymaker_PETG_PolyLite_flow_k': 0.015,
    'Polymaker_PETG_PolyLite_flow_k_min': 0.005,
    'Polymaker_PETG_PolyLite_flow_k_max': 0.045,
    'Polymaker_PETG_PolyLite_vol_speed': 12,

    # PETG-CF series
    'generic_PETG-CF_generic_load_temp': 270,
    'generic_PETG-CF_generic_unload_temp': 270,
    'generic_PETG-CF_generic_is_soft': False,

    'generic_PETG-CF_generic_print_temp': 255,
    'generic_PETG-CF_generic_flow_k': 0.02,
    'generic_PETG-CF_generic_flow_k_min': 0.005,
    'generic_PETG-CF_generic_flow_k_max': 0.045,
    'generic_PETG-CF_generic_vol_speed': 11,

    'Snapmaker_PETG-CF_generic_print_temp': 255,
    'Snapmaker_PETG-CF_generic_flow_k': 0.02,
    'Snapmaker_PETG-CF_generic_flow_k_min': 0.005,
    'Snapmaker_PETG-CF_generic_flow_k_max': 0.040,
    'Snapmaker_PETG-CF_generic_vol_speed': 14,

    # ABS series
    'generic_ABS_generic_load_temp': 280,
    'generic_ABS_generic_unload_temp': 280,
    'generic_ABS_generic_is_soft': False,

    'generic_ABS_generic_print_temp': 270,
    'generic_ABS_generic_flow_k': 0.012,
    'generic_ABS_generic_flow_k_min': 0.001,
    'generic_ABS_generic_flow_k_max': 0.045,
    'generic_ABS_generic_vol_speed': 15,

    'Snapmaker_ABS_generic_print_temp': 265,
    'Snapmaker_ABS_generic_flow_k': 0.01,
    'Snapmaker_ABS_generic_flow_k_min': 0.001,
    'Snapmaker_ABS_generic_flow_k_max': 0.030,
    'Snapmaker_ABS_generic_vol_speed': 18,

    'Polymaker_ABS_PolyLite_print_temp': 265,
    'Polymaker_ABS_PolyLite_flow_k': 0.01,
    'Polymaker_ABS_PolyLite_flow_k_min': 0.001,
    'Polymaker_ABS_PolyLite_flow_k_max': 0.030,
    'Polymaker_ABS_PolyLite_vol_speed': 18,

    # ASA series
    'generic_ASA_generic_load_temp': 280,
    'generic_ASA_generic_unload_temp': 280,
    'generic_ASA_generic_is_soft': False,

    'generic_ASA_generic_print_temp': 260,
    'generic_ASA_generic_flow_k': 0.012,
    'generic_ASA_generic_flow_k_min': 0.001,
    'generic_ASA_generic_flow_k_max': 0.045,
    'generic_ASA_generic_vol_speed': 12,

    'Snapmaker_ASA_generic_print_temp': 270,
    'Snapmaker_ASA_generic_flow_k': 0.015,
    'Snapmaker_ASA_generic_flow_k_min': 0.001,
    'Snapmaker_ASA_generic_flow_k_max': 0.035,
    'Snapmaker_ASA_generic_vol_speed': 18,

    # TPU series
    'generic_TPU_generic_load_temp': 250,
    'generic_TPU_generic_unload_temp': 250,
    'generic_TPU_generic_is_soft': True,
    'generic_TPU_generic_print_temp': 240,
    'generic_TPU_generic_flow_k': 0.2,
    'generic_TPU_generic_flow_k_min': 0.08,
    'generic_TPU_generic_flow_k_max': 0.35,
    'generic_TPU_generic_vol_speed': 3.2,

    'generic_TPU_90A_load_temp': 250,
    'generic_TPU_90A_unload_temp': 250,
    'generic_TPU_90A_is_soft': True,
    'generic_TPU_90A_print_temp': 230,
    'generic_TPU_90A_flow_k': 0.2,
    'generic_TPU_90A_flow_k_min': 0.08,
    'generic_TPU_90A_flow_k_max': 0.35,
    'generic_TPU_90A_vol_speed': 3.2,

    'generic_TPU_95A HF_load_temp': 250,
    'generic_TPU_95A HF_unload_temp': 250,
    'generic_TPU_95A HF_is_soft': True,
    'generic_TPU_95A HF_print_temp': 235,
    'generic_TPU_95A HF_flow_k': 0.15,
    'generic_TPU_95A HF_flow_k_min': 0.05,
    'generic_TPU_95A HF_flow_k_max': 0.25,
    'generic_TPU_95A HF_vol_speed': 10.5,

    'Snapmaker_TPU_90A_print_temp': 220,
    'Snapmaker_TPU_90A_flow_k': 0.4,
    'Snapmaker_TPU_90A_flow_k_min': 0.15,
    'Snapmaker_TPU_90A_flow_k_max': 0.45,
    'Snapmaker_TPU_90A_vol_speed': 3.2,

    'Snapmaker_TPU_95A HF_print_temp': 215,
    'Snapmaker_TPU_95A HF_flow_k': 0.14,
    'Snapmaker_TPU_95A HF_flow_k_min': 0.05,
    'Snapmaker_TPU_95A HF_flow_k_max': 0.25,
    'Snapmaker_TPU_95A HF_vol_speed': 12,

    # PA series
    'generic_PA_generic_load_temp': 280,
    'generic_PA_generic_unload_temp': 280,
    'generic_PA_generic_is_soft': False,
    'generic_PA_generic_print_temp': 260,
    'generic_PA_generic_flow_k': 0.012,
    'generic_PA_generic_flow_k_min': 0.001,
    'generic_PA_generic_flow_k_max': 0.045,
    'generic_PA_generic_vol_speed': 12,

    # PA-CF series
    'generic_PA-CF_generic_load_temp': 300,
    'generic_PA-CF_generic_unload_temp': 300,
    'generic_PA-CF_generic_is_soft': False,
    'generic_PA-CF_generic_print_temp': 290,
    'generic_PA-CF_generic_flow_k': 0.012,
    'generic_PA-CF_generic_flow_k_min': 0.001,
    'generic_PA-CF_generic_flow_k_max': 0.03,
    'generic_PA-CF_generic_vol_speed': 8,

    # PA6-CF series
    'generic_PA6-CF_generic_load_temp': 290,
    'generic_PA6-CF_generic_unload_temp': 290,
    'generic_PA6-CF_generic_is_soft': False,
    'generic_PA6-CF_generic_print_temp': 275,
    'generic_PA6-CF_generic_flow_k': 0.012,
    'generic_PA6-CF_generic_flow_k_min': 0.001,
    'generic_PA6-CF_generic_flow_k_max': 0.03,
    'generic_PA6-CF_generic_vol_speed': 8,

    # PA-GF series
    'generic_PA-GF_generic_load_temp': 300,
    'generic_PA-GF_generic_unload_temp': 300,
    'generic_PA-GF_generic_is_soft': False,
    'generic_PA-GF_generic_print_temp': 290,
    'generic_PA-GF_generic_flow_k': 0.012,
    'generic_PA-GF_generic_flow_k_min': 0.001,
    'generic_PA-GF_generic_flow_k_max': 0.03,
    'generic_PA-GF_generic_vol_speed': 8,

    # PA6-GF series
    'generic_PA6-GF_generic_load_temp': 280,
    'generic_PA6-GF_generic_unload_temp': 280,
    'generic_PA6-GF_generic_is_soft': False,
    'generic_PA6-GF_generic_print_temp': 265,
    'generic_PA6-GF_generic_flow_k': 0.012,
    'generic_PA6-GF_generic_flow_k_min': 0.001,
    'generic_PA6-GF_generic_flow_k_max': 0.03,
    'generic_PA6-GF_generic_vol_speed': 10.5,

    # PC series
    'generic_PC_generic_load_temp': 300,
    'generic_PC_generic_unload_temp': 300,
    'generic_PC_generic_is_soft': False,
    'generic_PC_generic_print_temp': 280,
    'generic_PC_generic_flow_k': 0.012,
    'generic_PC_generic_flow_k_min': 0.001,
    'generic_PC_generic_flow_k_max': 0.045,
    'generic_PC_generic_vol_speed': 16,

    # PC-ABS series
    'generic_PC-ABS_generic_load_temp': 300,
    'generic_PC-ABS_generic_unload_temp': 300,
    'generic_PC-ABS_generic_is_soft': False,
    'generic_PC-ABS_generic_print_temp': 280,
    'generic_PC-ABS_generic_flow_k': 0.012,
    'generic_PC-ABS_generic_flow_k_min': 0.005,
    'generic_PC-ABS_generic_flow_k_max': 0.045,
    'generic_PC-ABS_generic_vol_speed': 16,

    # PVA series
    'generic_PVA_generic_load_temp': 250,
    'generic_PVA_generic_unload_temp': 250,
    'generic_PVA_generic_is_soft': True,
    'generic_PVA_generic_print_temp': 220,
    'generic_PVA_generic_flow_k': 0.02,
    'generic_PVA_generic_flow_k_min': 0.005,
    'generic_PVA_generic_flow_k_max': 0.045,
    'generic_PVA_generic_vol_speed': 6,

    # PEBA series
    'generic_PEBA_generic_load_temp': 250,
    'generic_PEBA_generic_unload_temp': 250,
    'generic_PEBA_generic_is_soft': True,
    'generic_PEBA_generic_print_temp': 235,
    'generic_PEBA_generic_flow_k': 0.11,
    'generic_PEBA_generic_flow_k_min': 0.03,
    'generic_PEBA_generic_flow_k_max': 0.3,
    'generic_PEBA_generic_vol_speed': 15,

    'Snapmaker_PEBA_90A_print_temp': 240,
    'Snapmaker_PEBA_90A_flow_k': 0.11,
    'Snapmaker_PEBA_90A_flow_k_min': 0.03,
    'Snapmaker_PEBA_90A_flow_k_max': 0.3,
    'Snapmaker_PEBA_90A_vol_speed': 15,
}

FILAMENT_PARA_CFG_STANDARD_08_DEFAULT = {
    # generic parameters
    'version': FILAMENT_PARAMETER_VERSION,
    'hard_filaments_max_flow_k': 0.40,
    'soft_filaments_max_flow_k': 0.60,
    'process_print_accel': 5000,
    'process_print_slow_v': 20,

    # PLA series
    'generic_PLA_generic_load_temp': 250,
    'generic_PLA_generic_unload_temp': 250,
    'generic_PLA_generic_is_soft': False,

    'generic_PLA_generic_print_temp': 220,
    'generic_PLA_generic_flow_k': 0.008,
    'generic_PLA_generic_flow_k_min': 0.001,
    'generic_PLA_generic_flow_k_max': 0.025,
    'generic_PLA_generic_vol_speed': 12,

    'Snapmaker_PLA_Basic_print_temp': 220,
    'Snapmaker_PLA_Basic_flow_k': 0.008,
    'Snapmaker_PLA_Basic_flow_k_min': 0.001,
    'Snapmaker_PLA_Basic_flow_k_max': 0.025,
    'Snapmaker_PLA_Basic_vol_speed': 15,

    'Snapmaker_PLA_SnapSpeed_print_temp': 220,
    'Snapmaker_PLA_SnapSpeed_flow_k': 0.018,
    'Snapmaker_PLA_SnapSpeed_flow_k_min': 0.001,
    'Snapmaker_PLA_SnapSpeed_flow_k_max': 0.025,
    'Snapmaker_PLA_SnapSpeed_vol_speed': 20,

    'Snapmaker_PLA_Matte_print_temp': 215,
    'Snapmaker_PLA_Matte_flow_k': 0.015,
    'Snapmaker_PLA_Matte_flow_k_min': 0.001,
    'Snapmaker_PLA_Matte_flow_k_max': 0.025,
    'Snapmaker_PLA_Matte_vol_speed': 20,

    'Snapmaker_PLA_Silk_print_temp': 230,
    'Snapmaker_PLA_Silk_flow_k': 0.015,
    'Snapmaker_PLA_Silk_flow_k_min': 0.001,
    'Snapmaker_PLA_Silk_flow_k_max': 0.025,
    'Snapmaker_PLA_Silk_vol_speed': 10,

    'Snapmaker_PLA_Wood_print_temp': 220,
    'Snapmaker_PLA_Wood_flow_k': 0.007,
    'Snapmaker_PLA_Wood_flow_k_min': 0.001,
    'Snapmaker_PLA_Wood_flow_k_max': 0.025,
    'Snapmaker_PLA_Wood_vol_speed': 20,

    'Snapmaker_PLA_Translucent_print_temp': 220,
    'Snapmaker_PLA_Translucent_flow_k': 0.02,
    'Snapmaker_PLA_Translucent_flow_k_min': 0.001,
    'Snapmaker_PLA_Translucent_flow_k_max': 0.025,
    'Snapmaker_PLA_Translucent_vol_speed': 12,

    'Polymaker_PLA_PolyLite_print_temp': 220,
    'Polymaker_PLA_PolyLite_flow_k': 0.008,
    'Polymaker_PLA_PolyLite_flow_k_min': 0.001,
    'Polymaker_PLA_PolyLite_flow_k_max': 0.025,
    'Polymaker_PLA_PolyLite_vol_speed': 15,

    'Polymaker_PLA_PolySonic_print_temp': 220,
    'Polymaker_PLA_PolySonic_flow_k': 0.018,
    'Polymaker_PLA_PolySonic_flow_k_min': 0.001,
    'Polymaker_PLA_PolySonic_flow_k_max': 0.025,
    'Polymaker_PLA_PolySonic_vol_speed': 20,

    'Polymaker_PLA_PolyTerra_print_temp': 215,
    'Polymaker_PLA_PolyTerra_flow_k': 0.015,
    'Polymaker_PLA_PolyTerra_flow_k_min': 0.001,
    'Polymaker_PLA_PolyTerra_flow_k_max': 0.025,
    'Polymaker_PLA_PolyTerra_vol_speed': 20,

    # PLA-CF series
    'generic_PLA-CF_generic_load_temp': 250,
    'generic_PLA-CF_generic_unload_temp': 250,
    'generic_PLA-CF_generic_is_soft': False,

    'generic_PLA-CF_generic_print_temp': 220,
    'generic_PLA-CF_generic_flow_k': 0.008,
    'generic_PLA-CF_generic_flow_k_min': 0.001,
    'generic_PLA-CF_generic_flow_k_max': 0.025,
    'generic_PLA-CF_generic_vol_speed': 12,

    'Snapmaker_PLA-CF_generic_print_temp': 220,
    'Snapmaker_PLA-CF_generic_flow_k': 0.015,
    'Snapmaker_PLA-CF_generic_flow_k_min': 0.001,
    'Snapmaker_PLA-CF_generic_flow_k_max': 0.025,
    'Snapmaker_PLA-CF_generic_vol_speed': 18,

    # PETG series
    'generic_PETG_generic_load_temp': 270,
    'generic_PETG_generic_unload_temp': 270,
    'generic_PETG_generic_is_soft': False,

    'generic_PETG_generic_print_temp': 255,
    'generic_PETG_generic_flow_k': 0.01,
    'generic_PETG_generic_flow_k_min': 0.001,
    'generic_PETG_generic_flow_k_max': 0.03,
    'generic_PETG_generic_vol_speed': 12,

    'generic_PETG_HF_print_temp': 230,
    'generic_PETG_HF_flow_k': 0.008,
    'generic_PETG_HF_flow_k_min': 0.005,
    'generic_PETG_HF_flow_k_max': 0.030,
    'generic_PETG_HF_vol_speed': 16,

    'Snapmaker_PETG_generic_print_temp': 255,
    'Snapmaker_PETG_generic_flow_k': 0.01,
    'Snapmaker_PETG_generic_flow_k_min': 0.001,
    'Snapmaker_PETG_generic_flow_k_max': 0.030,
    'Snapmaker_PETG_generic_vol_speed': 12,

    'Snapmaker_PETG_HF_print_temp': 245,
    'Snapmaker_PETG_HF_flow_k': 0.02,
    'Snapmaker_PETG_HF_flow_k_min': 0.001,
    'Snapmaker_PETG_HF_flow_k_max': 0.025,
    'Snapmaker_PETG_HF_vol_speed': 20,

    'Snapmaker_PETG_Translucent_print_temp': 245,
    'Snapmaker_PETG_Translucent_flow_k': 0.02,
    'Snapmaker_PETG_Translucent_flow_k_min': 0.001,
    'Snapmaker_PETG_Translucent_flow_k_max': 0.03,
    'Snapmaker_PETG_Translucent_vol_speed': 16,

    'Polymaker_PETG_PolyLite_print_temp': 255,
    'Polymaker_PETG_PolyLite_flow_k': 0.01,
    'Polymaker_PETG_PolyLite_flow_k_min': 0.001,
    'Polymaker_PETG_PolyLite_flow_k_max': 0.03,
    'Polymaker_PETG_PolyLite_vol_speed': 12,

    # PETG-CF series
    'generic_PETG-CF_generic_load_temp': 270,
    'generic_PETG-CF_generic_unload_temp': 270,
    'generic_PETG-CF_generic_is_soft': False,

    'generic_PETG-CF_generic_print_temp': 255,
    'generic_PETG-CF_generic_flow_k': 0.01,
    'generic_PETG-CF_generic_flow_k_min': 0.001,
    'generic_PETG-CF_generic_flow_k_max': 0.020,
    'generic_PETG-CF_generic_vol_speed': 11,

    'Snapmaker_PETG-CF_generic_print_temp': 255,
    'Snapmaker_PETG-CF_generic_flow_k': 0.02,
    'Snapmaker_PETG-CF_generic_flow_k_min': 0.001,
    'Snapmaker_PETG-CF_generic_flow_k_max': 0.030,
    'Snapmaker_PETG-CF_generic_vol_speed': 14,

    # ABS series
    'generic_ABS_generic_load_temp': 280,
    'generic_ABS_generic_unload_temp': 280,
    'generic_ABS_generic_is_soft': False,

    'generic_ABS_generic_print_temp': 270,
    'generic_ABS_generic_flow_k': 0.008,
    'generic_ABS_generic_flow_k_min': 0.001,
    'generic_ABS_generic_flow_k_max': 0.030,
    'generic_ABS_generic_vol_speed': 15,

    'Snapmaker_ABS_generic_print_temp': 265,
    'Snapmaker_ABS_generic_flow_k': 0.01,
    'Snapmaker_ABS_generic_flow_k_min': 0.001,
    'Snapmaker_ABS_generic_flow_k_max': 0.030,
    'Snapmaker_ABS_generic_vol_speed': 20,

    'Polymaker_ABS_PolyLite_print_temp': 265,
    'Polymaker_ABS_PolyLite_flow_k': 0.01,
    'Polymaker_ABS_PolyLite_flow_k_min': 0.001,
    'Polymaker_ABS_PolyLite_flow_k_max': 0.030,
    'Polymaker_ABS_PolyLite_vol_speed': 20,

    # ASA series
    'generic_ASA_generic_load_temp': 280,
    'generic_ASA_generic_unload_temp': 280,
    'generic_ASA_generic_is_soft': False,

    'generic_ASA_generic_print_temp': 260,
    'generic_ASA_generic_flow_k': 0.008,
    'generic_ASA_generic_flow_k_min': 0.001,
    'generic_ASA_generic_flow_k_max': 0.030,
    'generic_ASA_generic_vol_speed': 15,

    'Snapmaker_ASA_generic_print_temp': 270,
    'Snapmaker_ASA_generic_flow_k': 0.015,
    'Snapmaker_ASA_generic_flow_k_min': 0.001,
    'Snapmaker_ASA_generic_flow_k_max': 0.030,
    'Snapmaker_ASA_generic_vol_speed': 18,

    # TPU series
    'generic_TPU_generic_load_temp': 250,
    'generic_TPU_generic_unload_temp': 250,
    'generic_TPU_generic_is_soft': True,
    'generic_TPU_generic_print_temp': 240,
    'generic_TPU_generic_flow_k': 0.17,
    'generic_TPU_generic_flow_k_min': 0.02,
    'generic_TPU_generic_flow_k_max': 0.3,
    'generic_TPU_generic_vol_speed': 3.2,

    'generic_TPU_90A_load_temp': 250,
    'generic_TPU_90A_unload_temp': 250,
    'generic_TPU_90A_is_soft': True,
    'generic_TPU_90A_print_temp': 230,
    'generic_TPU_90A_flow_k': 0.17,
    'generic_TPU_90A_flow_k_min': 0.08,
    'generic_TPU_90A_flow_k_max': 0.35,
    'generic_TPU_90A_vol_speed': 3.2,

    'generic_TPU_95A HF_load_temp': 250,
    'generic_TPU_95A HF_unload_temp': 250,
    'generic_TPU_95A HF_is_soft': True,
    'generic_TPU_95A HF_print_temp': 235,
    'generic_TPU_95A HF_flow_k': 0.13,
    'generic_TPU_95A HF_flow_k_min': 0.05,
    'generic_TPU_95A HF_flow_k_max': 0.25,
    'generic_TPU_95A HF_vol_speed': 10.5,

    'Snapmaker_TPU_90A_print_temp': 220,
    'Snapmaker_TPU_90A_flow_k': 0.4,
    'Snapmaker_TPU_90A_flow_k_min': 0.15,
    'Snapmaker_TPU_90A_flow_k_max': 0.45,
    'Snapmaker_TPU_90A_vol_speed': 3.5,

    'Snapmaker_TPU_95A HF_print_temp': 215,
    'Snapmaker_TPU_95A HF_flow_k': 0.12,
    'Snapmaker_TPU_95A HF_flow_k_min': 0.02,
    'Snapmaker_TPU_95A HF_flow_k_max': 0.25,
    'Snapmaker_TPU_95A HF_vol_speed': 16,

    # PA series
    'generic_PA_generic_load_temp': 280,
    'generic_PA_generic_unload_temp': 280,
    'generic_PA_generic_is_soft': False,
    'generic_PA_generic_print_temp': 260,
    'generic_PA_generic_flow_k': 0.008,
    'generic_PA_generic_flow_k_min': 0.001,
    'generic_PA_generic_flow_k_max': 0.03,
    'generic_PA_generic_vol_speed': 12,

    # PA-CF series
    'generic_PA-CF_generic_load_temp': 300,
    'generic_PA-CF_generic_unload_temp': 300,
    'generic_PA-CF_generic_is_soft': False,
    'generic_PA-CF_generic_print_temp': 290,
    'generic_PA-CF_generic_flow_k': 0.005,
    'generic_PA-CF_generic_flow_k_min': 0,
    'generic_PA-CF_generic_flow_k_max': 0.03,
    'generic_PA-CF_generic_vol_speed': 8,

    # PA6-CF series
    'generic_PA6-CF_generic_load_temp': 290,
    'generic_PA6-CF_generic_unload_temp': 290,
    'generic_PA6-CF_generic_is_soft': False,
    'generic_PA6-CF_generic_print_temp': 275,
    'generic_PA6-CF_generic_flow_k': 0.008,
    'generic_PA6-CF_generic_flow_k_min': 0.001,
    'generic_PA6-CF_generic_flow_k_max': 0.03,
    'generic_PA6-CF_generic_vol_speed': 8,

    'generic_PA-GF_generic_load_temp': 300,
    'generic_PA-GF_generic_unload_temp': 300,
    'generic_PA-GF_generic_is_soft': False,
    'generic_PA-GF_generic_print_temp': 290,
    'generic_PA-GF_generic_flow_k': 0.005,
    'generic_PA-GF_generic_flow_k_min': 0,
    'generic_PA-GF_generic_flow_k_max': 0.03,
    'generic_PA-GF_generic_vol_speed': 8,

    # PA6-GF series
    'generic_PA6-GF_generic_load_temp': 280,
    'generic_PA6-GF_generic_unload_temp': 280,
    'generic_PA6-GF_generic_is_soft': False,
    'generic_PA6-GF_generic_print_temp': 265,
    'generic_PA6-GF_generic_flow_k': 0.012,
    'generic_PA6-GF_generic_flow_k_min': 0.001,
    'generic_PA6-GF_generic_flow_k_max': 0.03,
    'generic_PA6-GF_generic_vol_speed': 10.5,

    # PC series
    'generic_PC_generic_load_temp': 300,
    'generic_PC_generic_unload_temp': 300,
    'generic_PC_generic_is_soft': False,
    'generic_PC_generic_print_temp': 280,
    'generic_PC_generic_flow_k': 0.008,
    'generic_PC_generic_flow_k_min': 0.001,
    'generic_PC_generic_flow_k_max': 0.03,
    'generic_PC_generic_vol_speed': 16,

    # PC-ABS series
    'generic_PC-ABS_generic_load_temp': 300,
    'generic_PC-ABS_generic_unload_temp': 300,
    'generic_PC-ABS_generic_is_soft': False,
    'generic_PC-ABS_generic_print_temp': 280,
    'generic_PC-ABS_generic_flow_k': 0.008,
    'generic_PC-ABS_generic_flow_k_min': 0.005,
    'generic_PC-ABS_generic_flow_k_max': 0.045,
    'generic_PC-ABS_generic_vol_speed': 16,

    'generic_PVA_generic_load_temp': 250,
    'generic_PVA_generic_unload_temp': 250,
    'generic_PVA_generic_is_soft': True,
    'generic_PVA_generic_print_temp': 220,
    'generic_PVA_generic_flow_k': 0.01,
    'generic_PVA_generic_flow_k_min': 0.001,
    'generic_PVA_generic_flow_k_max': 0.030,
    'generic_PVA_generic_vol_speed': 6,

    'generic_PEBA_generic_load_temp': 250,
    'generic_PEBA_generic_unload_temp': 250,
    'generic_PEBA_generic_is_soft': True,
    'generic_PEBA_generic_print_temp': 240,
    'generic_PEBA_generic_flow_k': 0.11,
    'generic_PEBA_generic_flow_k_min': 0.03,
    'generic_PEBA_generic_flow_k_max': 0.3,
    'generic_PEBA_generic_vol_speed': 15,

    'Snapmaker_PEBA_90A_print_temp': 240,
    'Snapmaker_PEBA_90A_flow_k': 0.08,
    'Snapmaker_PEBA_90A_flow_k_min': 0.02,
    'Snapmaker_PEBA_90A_flow_k_max': 0.3,
    'Snapmaker_PEBA_90A_vol_speed': 15,
}

FILAMENT_PARA_CFG_HIGH_FLOW_04_DEFAULT = {
    'version': FILAMENT_PARAMETER_VERSION,
    'hard_filaments_max_flow_k': 0.40,
    'soft_filaments_max_flow_k': 0.60,
    'process_print_accel': 5000,
    'process_print_slow_v': 20,

    'generic_PLA_generic_load_temp': 250,
    'generic_PLA_generic_unload_temp': 250,
    'generic_PLA_generic_is_soft': False,
    'generic_PLA_generic_print_temp': 220,
    'generic_PLA_generic_flow_k': 0.02,
    'generic_PLA_generic_flow_k_min': 0.005,
    'generic_PLA_generic_flow_k_max': 0.040,
    'generic_PLA_generic_vol_speed': 12,

    'Snapmaker_PLA_Basic_print_temp': 220,
    'Snapmaker_PLA_Basic_flow_k': 0.02,
    'Snapmaker_PLA_Basic_flow_k_min': 0.005,
    'Snapmaker_PLA_Basic_flow_k_max': 0.040,
    'Snapmaker_PLA_Basic_vol_speed': 15,

    'Snapmaker_PLA_SnapSpeed_print_temp': 220,
    'Snapmaker_PLA_SnapSpeed_flow_k': 0.027,
    'Snapmaker_PLA_SnapSpeed_flow_k_min': 0.005,
    'Snapmaker_PLA_SnapSpeed_flow_k_max': 0.040,
    'Snapmaker_PLA_SnapSpeed_vol_speed': 40,

    'Snapmaker_PLA_Matte_print_temp': 220,
    'Snapmaker_PLA_Matte_flow_k': 0.02,
    'Snapmaker_PLA_Matte_flow_k_min': 0.005,
    'Snapmaker_PLA_Matte_flow_k_max': 0.040,
    'Snapmaker_PLA_Matte_vol_speed': 40,

    'Snapmaker_PLA_Silk_print_temp': 230,
    'Snapmaker_PLA_Silk_flow_k': 0.015,
    'Snapmaker_PLA_Silk_flow_k_min': 0.005,
    'Snapmaker_PLA_Silk_flow_k_max': 0.035,
    'Snapmaker_PLA_Silk_vol_speed': 12,

    'Polymaker_PLA_PolySonic_print_temp': 220,
    'Polymaker_PLA_PolySonic_flow_k': 0.027,
    'Polymaker_PLA_PolySonic_flow_k_min': 0.005,
    'Polymaker_PLA_PolySonic_flow_k_max': 0.040,
    'Polymaker_PLA_PolySonic_vol_speed': 40,

    'Polymaker_PLA_PolyTerra_print_temp': 220,
    'Polymaker_PLA_PolyTerra_flow_k': 0.02,
    'Polymaker_PLA_PolyTerra_flow_k_min': 0.005,
    'Polymaker_PLA_PolyTerra_flow_k_max': 0.040,
    'Polymaker_PLA_PolyTerra_vol_speed': 40,

    'generic_PLA-CF_generic_load_temp': 250,
    'generic_PLA-CF_generic_unload_temp': 250,
    'generic_PLA-CF_generic_is_soft': False,
    'generic_PLA-CF_generic_print_temp': 220,
    'generic_PLA-CF_generic_flow_k': 0.02,
    'generic_PLA-CF_generic_flow_k_min': 0.005,
    'generic_PLA-CF_generic_flow_k_max': 0.040,
    'generic_PLA-CF_generic_vol_speed': 12,

    'generic_PETG_generic_load_temp': 270,
    'generic_PETG_generic_unload_temp': 270,
    'generic_PETG_generic_is_soft': False,
    'generic_PETG_generic_print_temp': 255,
    'generic_PETG_generic_flow_k': 0.04,
    'generic_PETG_generic_flow_k_min': 0.005,
    'generic_PETG_generic_flow_k_max': 0.040,
    'generic_PETG_generic_vol_speed': 12,

    'generic_PETG_HF_print_temp': 230,
    'generic_PETG_HF_flow_k': 0.04,
    'generic_PETG_HF_flow_k_min': 0.005,
    'generic_PETG_HF_flow_k_max': 0.040,
    'generic_PETG_HF_vol_speed': 16,

    'Snapmaker_PETG_HF_print_temp': 245,
    'Snapmaker_PETG_HF_flow_k': 0.035,
    'Snapmaker_PETG_HF_flow_k_min': 0.015,
    'Snapmaker_PETG_HF_flow_k_max': 0.040,
    'Snapmaker_PETG_HF_vol_speed': 30,

    'generic_ABS_generic_load_temp': 280,
    'generic_ABS_generic_unload_temp': 280,
    'generic_ABS_generic_is_soft': False,
    'generic_ABS_generic_print_temp': 270,
    'generic_ABS_generic_flow_k': 0.02,
    'generic_ABS_generic_flow_k_min': 0.005,
    'generic_ABS_generic_flow_k_max': 0.040,
    'generic_ABS_generic_vol_speed': 15,

    'Snapmaker_ABS_generic_print_temp': 270,
    'Snapmaker_ABS_generic_flow_k': 0.02,
    'Snapmaker_ABS_generic_flow_k_min': 0.005,
    'Snapmaker_ABS_generic_flow_k_max': 0.035,
    'Snapmaker_ABS_generic_vol_speed': 25,

    'generic_ASA_generic_load_temp': 280,
    'generic_ASA_generic_unload_temp': 280,
    'generic_ASA_generic_is_soft': False,
    'generic_ASA_generic_print_temp': 260,
    'generic_ASA_generic_flow_k': 0.02,
    'generic_ASA_generic_flow_k_min': 0.005,
    'generic_ASA_generic_flow_k_max': 0.040,
    'generic_ASA_generic_vol_speed': 12,

    'generic_TPU_generic_load_temp': 250,
    'generic_TPU_generic_unload_temp': 250,
    'generic_TPU_generic_is_soft': True,
    'generic_TPU_generic_print_temp': 240,
    'generic_TPU_generic_flow_k': 0.4,
    'generic_TPU_generic_flow_k_min': 0.15,
    'generic_TPU_generic_flow_k_max': 0.45,
    'generic_TPU_generic_vol_speed': 3.2,

    'generic_TPU_90A_load_temp': 250,
    'generic_TPU_90A_unload_temp': 250,
    'generic_TPU_90A_is_soft': True,
    'generic_TPU_90A_print_temp': 230,
    'generic_TPU_90A_flow_k': 0.4,
    'generic_TPU_90A_flow_k_min': 0.15,
    'generic_TPU_90A_flow_k_max': 0.45,
    'generic_TPU_90A_vol_speed': 3.2,

    'generic_TPU_95A HF_load_temp': 250,
    'generic_TPU_95A HF_unload_temp': 250,
    'generic_TPU_95A HF_is_soft': True,
    'generic_TPU_95A HF_print_temp': 235,
    'generic_TPU_95A HF_flow_k': 0.15,
    'generic_TPU_95A HF_flow_k_min': 0.05,
    'generic_TPU_95A HF_flow_k_max': 0.25,
    'generic_TPU_95A HF_vol_speed': 10.5,

    'generic_PA_generic_load_temp': 280,
    'generic_PA_generic_unload_temp': 280,
    'generic_PA_generic_is_soft': False,
    'generic_PA_generic_print_temp': 260,
    'generic_PA_generic_flow_k': 0.02,
    'generic_PA_generic_flow_k_min': 0.005,
    'generic_PA_generic_flow_k_max': 0.040,
    'generic_PA_generic_vol_speed': 12,

    'generic_PA-CF_generic_load_temp': 300,
    'generic_PA-CF_generic_unload_temp': 300,
    'generic_PA-CF_generic_is_soft': False,
    'generic_PA-CF_generic_print_temp': 290,
    'generic_PA-CF_generic_flow_k': 0.02,
    'generic_PA-CF_generic_flow_k_min': 0.005,
    'generic_PA-CF_generic_flow_k_max': 0.040,
    'generic_PA-CF_generic_vol_speed': 8,

    'generic_PA6-CF_generic_load_temp': 290,
    'generic_PA6-CF_generic_unload_temp': 290,
    'generic_PA6-CF_generic_is_soft': False,
    'generic_PA6-CF_generic_print_temp': 275,
    'generic_PA6-CF_generic_flow_k': 0.02,
    'generic_PA6-CF_generic_flow_k_min': 0.005,
    'generic_PA6-CF_generic_flow_k_max': 0.040,
    'generic_PA6-CF_generic_vol_speed': 8,

    'generic_PA-GF_generic_load_temp': 300,
    'generic_PA-GF_generic_unload_temp': 300,
    'generic_PA-GF_generic_is_soft': False,
    'generic_PA-GF_generic_print_temp': 290,
    'generic_PA-GF_generic_flow_k': 0.02,
    'generic_PA-GF_generic_flow_k_min': 0.005,
    'generic_PA-GF_generic_flow_k_max': 0.040,
    'generic_PA-GF_generic_vol_speed': 8,

    'generic_PA6-GF_generic_load_temp': 280,
    'generic_PA6-GF_generic_unload_temp': 280,
    'generic_PA6-GF_generic_is_soft': False,
    'generic_PA6-GF_generic_print_temp': 265,
    'generic_PA6-GF_generic_flow_k': 0.02,
    'generic_PA6-GF_generic_flow_k_min': 0.005,
    'generic_PA6-GF_generic_flow_k_max': 0.040,
    'generic_PA6-GF_generic_vol_speed': 10.5,

    'generic_PC_generic_load_temp': 300,
    'generic_PC_generic_unload_temp': 300,
    'generic_PC_generic_is_soft': False,
    'generic_PC_generic_print_temp': 280,
    'generic_PC_generic_flow_k': 0.02,
    'generic_PC_generic_flow_k_min': 0.005,
    'generic_PC_generic_flow_k_max': 0.040,
    'generic_PC_generic_vol_speed': 16,

    'generic_PC-ABS_generic_load_temp': 300,
    'generic_PC-ABS_generic_unload_temp': 300,
    'generic_PC-ABS_generic_is_soft': False,
    'generic_PC-ABS_generic_print_temp': 280,
    'generic_PC-ABS_generic_flow_k': 0.02,
    'generic_PC-ABS_generic_flow_k_min': 0.005,
    'generic_PC-ABS_generic_flow_k_max': 0.040,
    'generic_PC-ABS_generic_vol_speed': 16,

    'generic_PVA_generic_load_temp': 250,
    'generic_PVA_generic_unload_temp': 250,
    'generic_PVA_generic_is_soft': True,
    'generic_PVA_generic_print_temp': 240,
    'generic_PVA_generic_flow_k': 0.028,
    'generic_PVA_generic_flow_k_min': 0.01,
    'generic_PVA_generic_flow_k_max': 0.065,
    'generic_PVA_generic_vol_speed': 6,

    'generic_PEBA_generic_load_temp': 250,
    'generic_PEBA_generic_unload_temp': 250,
    'generic_PEBA_generic_is_soft': True,
    'generic_PEBA_generic_print_temp': 235,
    'generic_PEBA_generic_flow_k': 0.4,
    'generic_PEBA_generic_flow_k_min': 0.15,
    'generic_PEBA_generic_flow_k_max': 0.45,
    'generic_PEBA_generic_vol_speed': 5,
}


class FilamentParameters:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        config_dir = self.printer.get_snapmaker_config_dir()
        config_name = FILAMENT_PARA_STANDARD_02_CFG_FILE
        self._config_standard_02_path = os.path.join(config_dir, config_name)
        self._config_standard_02 = self.printer.load_snapmaker_config_file(
                            self._config_standard_02_path,
                            FILAMENT_PARA_CFG_STANDARD_02_DEFAULT,
                            create_if_not_exist=True)
        config_name = FILAMENT_PARA_STANDARD_04_CFG_FILE
        self._config_standard_04_path = os.path.join(config_dir, config_name)
        self._config_standard_04 = self.printer.load_snapmaker_config_file(
                            self._config_standard_04_path,
                            FILAMENT_PARA_CFG_STANDARD_04_DEFAULT,
                            create_if_not_exist=True)
        config_name = FILAMENT_PARA_STANDARD_06_CFG_FILE
        self._config_standard_06_path = os.path.join(config_dir, config_name)
        self._config_standard_06 = self.printer.load_snapmaker_config_file(
                            self._config_standard_06_path,
                            FILAMENT_PARA_CFG_STANDARD_06_DEFAULT,
                            create_if_not_exist=True)
        config_name = FILAMENT_PARA_STANDARD_08_CFG_FILE
        self._config_standard_08_path = os.path.join(config_dir, config_name)
        self._config_standard_08 = self.printer.load_snapmaker_config_file(
                            self._config_standard_08_path,
                            FILAMENT_PARA_CFG_STANDARD_08_DEFAULT,
                            create_if_not_exist=True)
        config_name = FILAMENT_PARA_HIGH_FLOW_04_CFG_FILE
        self._config_high_flow_04_path = os.path.join(config_dir, config_name)
        self._config_high_flow_04 = self.printer.load_snapmaker_config_file(
                            self._config_high_flow_04_path,
                            FILAMENT_PARA_CFG_HIGH_FLOW_04_DEFAULT,
                            create_if_not_exist=True)

        gcode = self.printer.lookup_object('gcode')
        gcode.register_command('FILAMENT_PARA_GET_ALL_INFO',
                               self.cmd_FILAMENT_PARA_GET_ALL_INFO)
        self.printer.register_event_handler("klippy:ready", self._ready)

    def _ready(self):
        dest_version = self._version_to_tuple(FILAMENT_PARAMETER_VERSION)
        version = self._config_standard_02.get('version', None)
        if version is None or self._version_to_tuple(version) < dest_version:
            logging.info("[filament_parameters] reset filament parameters standard_02")
            self._config_standard_02 = copy.deepcopy(FILAMENT_PARA_CFG_STANDARD_02_DEFAULT)
            self.printer.update_snapmaker_config_file(self._config_standard_02_path, self._config_standard_02, FILAMENT_PARA_CFG_STANDARD_02_DEFAULT)
        version = self._config_standard_04.get('version', None)
        if version is None or self._version_to_tuple(version) < dest_version:
            logging.info("[filament_parameters] reset filament parameters standard_04")
            self._config_standard_04 = copy.deepcopy(FILAMENT_PARA_CFG_STANDARD_04_DEFAULT)
            self.printer.update_snapmaker_config_file(self._config_standard_04_path, self._config_standard_04, FILAMENT_PARA_CFG_STANDARD_04_DEFAULT)
        version = self._config_standard_06.get('version', None)
        if version is None or self._version_to_tuple(version) < dest_version:
            logging.info("[filament_parameters] reset filament parameters standard_06")
            self._config_standard_06 = copy.deepcopy(FILAMENT_PARA_CFG_STANDARD_06_DEFAULT)
            self.printer.update_snapmaker_config_file(self._config_standard_06_path, self._config_standard_06, FILAMENT_PARA_CFG_STANDARD_06_DEFAULT)
        version = self._config_standard_08.get('version', None)
        if version is None or self._version_to_tuple(version) < dest_version:
            logging.info("[filament_parameters] reset filament parameters standard_08")
            self._config_standard_08 = copy.deepcopy(FILAMENT_PARA_CFG_STANDARD_08_DEFAULT)
            self.printer.update_snapmaker_config_file(self._config_standard_08_path, self._config_standard_08, FILAMENT_PARA_CFG_STANDARD_08_DEFAULT)
        version = self._config_high_flow_04.get('version', None)
        if version is None or self._version_to_tuple(version) < dest_version:
            logging.info("[filament_parameters] reset filament parameters high_flow_04")
            self._config_high_flow_04 = copy.deepcopy(FILAMENT_PARA_CFG_HIGH_FLOW_04_DEFAULT)
            self.printer.update_snapmaker_config_file(self._config_high_flow_04_path, self._config_high_flow_04, FILAMENT_PARA_CFG_HIGH_FLOW_04_DEFAULT)

    def _version_to_tuple(self, version_str):
        return tuple(map(int, version_str.split('.')))

    def get_status(self, eventtime=None):
        return {}

    def _search_filament_param_value(self, dict_obj, filament_vendor, filament_main_type, filament_sub_type, key_name):
        key = f'{filament_vendor}_{filament_main_type}_{filament_sub_type}_{key_name}'
        default_fill = 'generic'

        if key in dict_obj:
            return dict_obj[key]

        key = f'{filament_vendor}_{filament_main_type}_{default_fill}_{key_name}'
        if key in dict_obj:
            return dict_obj[key]

        key = f'{default_fill}_{filament_main_type}_{filament_sub_type}_{key_name}'
        if key in dict_obj:
            return dict_obj[key]

        key = f'{default_fill}_{filament_main_type}_{default_fill}_{key_name}'
        if key in dict_obj:
            return dict_obj[key]

        return None

    def get_filament_parameters(self, filament_vendor, filament_main_type, filament_sub_type,
                        nozzle_diameter=0.4, nozzle_volume_type='standard'):
        filament_parameters = {
            'load_temp': FILAMENT_LOAD_TEMP_UNKNOWN,
            'unload_temp': FILAMENT_UNLOAD_TEMP_UNKNOWN,
            'is_soft': FILAMENT_IS_SOFT_UNKNOWN,
            'print_temp': FILAMENT_FLOW_TEMP_UNKNOWN,
            'flow_k': FILAMENT_FLOW_K_UNKNOWN,
            'flow_k_min': FILAMENT_FLOW_K_MIN_UNKNOWN,
            'flow_k_max': FILAMENT_FLOW_K_MAX_UNKNOWN,
            'accel': FILAMENT_FLOW_ACCEL_UNKNOWN,
            'slow_v': FILAMENT_FLOW_SLOW_V_UNKNOWN,
            'fast_v': FILAMENT_FLOW_FAST_V_UNKNOWN,
            'max_flow_k': 1.0,
            'soft_filaments_max_flow_k': 1.0,
            'hard_filaments_max_flow_k': 1.0,
        }
        filament_parameters_unknown_1 = copy.deepcopy(filament_parameters)

        try:
            config = None
            line_area = None
            if nozzle_diameter > 0.1999 and nozzle_diameter < 0.2001:
                filament_parameters['flow_k'] = FILAMENT_FLOW_K_UNKNOWN_02
                filament_parameters['flow_k_min'] = FILAMENT_FLOW_K_MIN_UNKNOWN_02
                filament_parameters['flow_k_max'] = FILAMENT_FLOW_K_MAX_UNKNOWN_02
                filament_parameters['accel'] = FILAMENT_FLOW_ACCEL_UNKNOWN_02
                filament_parameters['slow_v'] = FILAMENT_FLOW_SLOW_V_UNKNOWN_02
                filament_parameters['fast_v'] = FILAMENT_FLOW_FAST_V_UNKNOWN_02
                config = self._config_standard_02
                line_area = 0.1 * (0.22 - 0.1 * (1 - 3.1415926 / 4.0))

            elif nozzle_diameter > 0.3999 and nozzle_diameter < 0.4001:
                filament_parameters['flow_k'] = FILAMENT_FLOW_K_UNKNOWN_04
                filament_parameters['flow_k_min'] = FILAMENT_FLOW_K_MIN_UNKNOWN_04
                filament_parameters['flow_k_max'] = FILAMENT_FLOW_K_MAX_UNKNOWN_04
                filament_parameters['accel'] = FILAMENT_FLOW_ACCEL_UNKNOWN_04
                filament_parameters['slow_v'] = FILAMENT_FLOW_SLOW_V_UNKNOWN_04
                filament_parameters['fast_v'] = FILAMENT_FLOW_FAST_V_UNKNOWN_04
                if nozzle_volume_type == 'high_flow':
                    config = self._config_high_flow_04
                else:
                    config = self._config_standard_04
                line_area = 0.2 * (0.42 - 0.2 * (1 - 3.1415926 / 4.0))

            elif nozzle_diameter > 0.5999 and nozzle_diameter < 0.6001:
                filament_parameters['flow_k'] = FILAMENT_FLOW_K_UNKNOWN_06
                filament_parameters['flow_k_min'] = FILAMENT_FLOW_K_MIN_UNKNOWN_06
                filament_parameters['flow_k_max'] = FILAMENT_FLOW_K_MAX_UNKNOWN_06
                filament_parameters['accel'] = FILAMENT_FLOW_ACCEL_UNKNOWN_06
                filament_parameters['slow_v'] = FILAMENT_FLOW_SLOW_V_UNKNOWN_06
                filament_parameters['fast_v'] = FILAMENT_FLOW_FAST_V_UNKNOWN_06
                config = self._config_standard_06
                line_area = 0.3 * (0.62 - 0.3 * (1 - 3.1415926 / 4.0))

            elif nozzle_diameter > 0.7999 and nozzle_diameter < 0.8001:
                filament_parameters['flow_k'] = FILAMENT_FLOW_K_UNKNOWN_08
                filament_parameters['flow_k_min'] = FILAMENT_FLOW_K_MIN_UNKNOWN_08
                filament_parameters['flow_k_max'] = FILAMENT_FLOW_K_MAX_UNKNOWN_08
                filament_parameters['accel'] = FILAMENT_FLOW_ACCEL_UNKNOWN_08
                filament_parameters['slow_v'] = FILAMENT_FLOW_SLOW_V_UNKNOWN_08
                filament_parameters['fast_v'] = FILAMENT_FLOW_FAST_V_UNKNOWN_08
                config = self._config_standard_08
                line_area = 0.4 * (0.82 - 0.4 * (1 - 3.1415926 / 4.0))

            else:
                return filament_parameters_unknown_1

            filament_parameters_unknown_2 = copy.deepcopy(filament_parameters)
            if filament_vendor == 'NONE' or filament_vendor == None or \
                filament_main_type == 'NONE' or filament_main_type == None:
                return filament_parameters_unknown_2

            try:
                value = self._search_filament_param_value(config, filament_vendor, filament_main_type, filament_sub_type, 'load_temp')
                if value != None and value > 0:
                    filament_parameters['load_temp'] = value

                value = self._search_filament_param_value(config, filament_vendor, filament_main_type, filament_sub_type, 'unload_temp')
                if value != None and value > 0:
                    filament_parameters['unload_temp'] = value

                value = self._search_filament_param_value(config, filament_vendor, filament_main_type, filament_sub_type, 'is_soft')
                if value != None:
                    filament_parameters['is_soft'] = value

                value = self._search_filament_param_value(config, filament_vendor, filament_main_type, filament_sub_type, 'print_temp')
                if value != None and value > 0:
                    filament_parameters['print_temp'] = value

                value = self._search_filament_param_value(config, filament_vendor, filament_main_type, filament_sub_type, 'flow_k')
                if value != None and value >= 0:
                    filament_parameters['flow_k'] = value

                value = self._search_filament_param_value(config, filament_vendor, filament_main_type, filament_sub_type, 'flow_k_min')
                if value != None and value >= 0:
                    filament_parameters['flow_k_min'] = value

                value = self._search_filament_param_value(config, filament_vendor, filament_main_type, filament_sub_type, 'flow_k_max')
                if value != None and value >= 0:
                    filament_parameters['flow_k_max'] = value

                filament_parameters['soft_filaments_max_flow_k'] = config.get('soft_filaments_max_flow_k', 1.0)
                filament_parameters['hard_filaments_max_flow_k'] = config.get('hard_filaments_max_flow_k', 1.0)
                if filament_parameters['is_soft']:
                    filament_parameters['max_flow_k'] = filament_parameters['soft_filaments_max_flow_k']
                else:
                    filament_parameters['max_flow_k'] = filament_parameters['hard_filaments_max_flow_k']

                vol_speed = self._search_filament_param_value(config, filament_vendor, filament_main_type, filament_sub_type, 'vol_speed')
                if vol_speed == None or vol_speed <= 0:
                    raise ValueError("vol_speed <= 0")

                process_print_accel = config['process_print_accel']
                if process_print_accel <= 0:
                    raise ValueError("process_print_accel <= 0")
                process_print_slow_v = config['process_print_slow_v']
                if process_print_slow_v <= 0:
                    raise ValueError("process_print_slow_v <= 0")
                accel = process_print_accel * line_area / 2.4053
                slow_v = process_print_slow_v * line_area / 2.4053
                fast_v = vol_speed / 2.4053
                if fast_v <= slow_v:
                    raise ValueError("fast_v <= slow_v")

                filament_parameters['accel'] = accel
                filament_parameters['slow_v'] = slow_v
                filament_parameters['fast_v'] = fast_v

                return filament_parameters

            except Exception as e:
                logging.error(e)
                return filament_parameters_unknown_2

        except Exception as e:
            logging.error("[filament_parameters] Failed to get filament parameters: %s", str(e))
            return filament_parameters_unknown_1

    def get_load_temp(self, filament_vendor, filament_main_type, filament_sub_type,
                      nozzle_diameter=0.4, nozzle_volume_type='standard'):
        parameter = self.get_filament_parameters(filament_vendor, filament_main_type, filament_sub_type,
                                                 nozzle_diameter, nozzle_volume_type)
        return parameter.get('load_temp', FILAMENT_LOAD_TEMP_UNKNOWN)

    def get_unload_temp(self, filament_vendor, filament_main_type, filament_sub_type,
                        nozzle_diameter=0.4, nozzle_volume_type='standard'):
        parameter = self.get_filament_parameters(filament_vendor, filament_main_type, filament_sub_type,
                                                 nozzle_diameter, nozzle_volume_type)
        return parameter.get('unload_temp', FILAMENT_UNLOAD_TEMP_UNKNOWN)

    def get_is_soft(self, filament_vendor, filament_main_type, filament_sub_type,
                        nozzle_diameter=0.4, nozzle_volume_type='standard'):
        parameter = self.get_filament_parameters(filament_vendor, filament_main_type, filament_sub_type,
                                                 nozzle_diameter, nozzle_volume_type)
        return parameter.get('is_soft', FILAMENT_IS_SOFT_UNKNOWN)

    def get_print_temp(self, filament_vendor, filament_main_type, filament_sub_type,
                       nozzle_diameter, nozzle_volume_type):
        parameter = self.get_filament_parameters(filament_vendor, filament_main_type, filament_sub_type,
                                                 nozzle_diameter, nozzle_volume_type)
        return parameter.get('print_temp', FILAMENT_FLOW_TEMP_UNKNOWN)

    def get_flow_k(self, filament_vendor, filament_main_type, filament_sub_type,
                        nozzle_diameter, nozzle_volume_type):
        parameter = self.get_filament_parameters(filament_vendor, filament_main_type, filament_sub_type,
                                                 nozzle_diameter, nozzle_volume_type)
        return parameter.get('flow_k', FILAMENT_FLOW_K_UNKNOWN)

    def is_allow_to_print(self, filament_vendor, filament_main_type, filament_sub_type,
                                   nozzle_diameter, nozzle_volume_type=None):
        is_allow = True
        try:
            if nozzle_diameter > 0.1999 and nozzle_diameter < 0.2001:
                if filament_main_type in FORBIDDEN_FILAMENT_TYPES_02:
                    value = FORBIDDEN_FILAMENT_TYPES_02.get(filament_main_type)
                    if '*' in value:
                        is_allow = False
                    else:
                        if filament_sub_type in value:
                            is_allow = False
                if filament_main_type.startswith('PA') or filament_main_type.startswith('PC') or \
                    '-CF' in filament_main_type or '-GF' in filament_main_type:
                    is_allow = False
            else:
                is_allow = True

        except Exception:
            is_allow = False

        return is_allow

    def cmd_FILAMENT_PARA_GET_ALL_INFO(self, gcmd):
        gcmd.respond_info("[filament_parameters] get all filament parameters")
        gcmd.respond_info(str(self._config_standard_02))
        gcmd.respond_info(str(self._config_standard_04))
        gcmd.respond_info(str(self._config_standard_06))
        gcmd.respond_info(str(self._config_standard_08))
        gcmd.respond_info(str(self._config_high_flow_04))

def load_config(config):
    return FilamentParameters(config)

