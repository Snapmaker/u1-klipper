import copy
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature

FILAMENT_INFO_STRUCT = {
    'VERSION': 0,
    'VENDOR': 'NONE', # Brand Owner
    'MANUFACTURER': 'NONE',
    'MAIN_TYPE': 'NONE',
    'SUB_TYPE': 'NONE',
    'TRAY': 0,
    'ALPHA': 0xFF,
    'COLOR_NUMS': 1,
    'ARGB_COLOR': 0xFFFFFFFF, # Old version
    'RGB_1': 0xFFFFFF,
    'RGB_2': 0,
    'RGB_3': 0,
    'RGB_4': 0,
    'RGB_5': 0,
    'DIAMETER': 0,
    'WEIGHT': 0,
    'LENGTH': 0,
    'DRYING_TEMP': 0,
    'DRYING_TIME': 0,
    'HOTEND_MAX_TEMP': 0,
    'HOTEND_MIN_TEMP': 0,
    'BED_TYPE': 0,
    'BED_TEMP': 0,
    'FIRST_LAYER_TEMP': 0,
    'OTHER_LAYER_TEMP': 0,
    'SKU': 0,
    'MF_DATE': '19700101',
    'RSA_KEY_VERSION': 0,
    'OFFICIAL': False,
    'CARD_UID': 0,
}

# Filament main type
FILAMENT_PROTO_MAIN_TYPE_RESERVED               = 0
FILAMENT_PROTO_MAIN_TYPE_PLA                    = 1
FILAMENT_PROTO_MAIN_TYPE_PETG                   = 2
FILAMENT_PROTO_MAIN_TYPE_ABS                    = 3
FILAMENT_PROTO_MAIN_TYPE_TPU                    = 4
FILAMENT_PROTO_MAIN_TYPE_PVA                    = 5

FILAMENT_PROTO_MAIN_TYPE_MAPPING = {
    "PLA":          FILAMENT_PROTO_MAIN_TYPE_PLA,
    "PETG":         FILAMENT_PROTO_MAIN_TYPE_PETG,
    "ABS":          FILAMENT_PROTO_MAIN_TYPE_ABS,
    "TPU":          FILAMENT_PROTO_MAIN_TYPE_TPU,
    "PVA":          FILAMENT_PROTO_MAIN_TYPE_PVA,
    "Reserved":     FILAMENT_PROTO_MAIN_TYPE_RESERVED
}

#Filament sub type
FILAMENT_PROTO_SUB_TYPE_RESERVED                = 0
FILAMENT_PROTO_SUB_TYPE_BASIC                   = 1
FILAMENT_PROTO_SUB_TYPE_MATTE                   = 2
FILAMENT_PROTO_SUB_TYPE_SNAPSPEED               = 3
FILAMENT_PROTO_SUB_TYPE_SILK                    = 4
FILAMENT_PROTO_SUB_TYPE_SUPPORT                 = 5
FILAMENT_PROTO_SUB_TYPE_HF                      = 6
FILAMENT_PROTO_SUB_TYPE_95A                     = 7
FILAMENT_PROTO_SUB_TYPE_95A_HF                  = 8

FILAMENT_PROTO_SUB_TYPE_MAPPING = {
    'Basic':        FILAMENT_PROTO_SUB_TYPE_BASIC,
    'Matte':        FILAMENT_PROTO_SUB_TYPE_MATTE,
    'SnapSpeed':    FILAMENT_PROTO_SUB_TYPE_SNAPSPEED,
    'Silk':         FILAMENT_PROTO_SUB_TYPE_SILK,
    'Support':      FILAMENT_PROTO_SUB_TYPE_SUPPORT,
    'HF':           FILAMENT_PROTO_SUB_TYPE_HF,
    '95A':          FILAMENT_PROTO_SUB_TYPE_95A,
    '95A HF':       FILAMENT_PROTO_SUB_TYPE_95A_HF,
    'Reserved':     FILAMENT_PROTO_SUB_TYPE_RESERVED
}

# Filament color nums
FILAMENT_PROTO_COLOR_NUMS_MAX                   = 5

# Filament Tag type
FILAMENT_PROTO_TAG_M1                           = 'M1_1K'
FILAMENT_PROTO_TAG_NTAG                         = 'NTAG'

# Material types supported for NTAG NDEF parsing
# Must match keys in filament_parameters.FILAMENT_PARA_CFG_DEFAULT
NTAG_SUPPORTED_MATERIAL_TYPES = {
    'PLA', 'PLA-CF', 'PETG', 'PETG-CF', 'PETG-HF', 'PCTG',
    'ABS', 'ASA', 'TPU', 'PVA', 'PA', 'PA-CF', 'PA6-CF',
    'PA-GF', 'PA6-GF', 'PC', 'PC-ABS', 'EVA',
}

# M1 card protocol
M1_PROTO_TOTAL_SIZE                             = 1024
## position : section_num * 64 + block_nom * 16 + byte_num
# Section 0
M1_PROTO_UID_POS                                = (0 * 64 + 0 * 16 + 0)
M1_PROTO_UID_LEN                                = (4)
M1_PROTO_VENDOR_POS                             = (0 * 64 + 1 * 16 + 0)
M1_PROTO_VENDOR_LEN                             = (16)
M1_PROTO_MANUFACTURER_POS                       = (0 * 64 + 2 * 16 + 0)
M1_PROTO_MANUFACTURER_LEN                       = (16)
# Section 1
M1_PROTO_VERSION_POS                            = (1 * 64 + 0 * 16 + 0)
M1_PROTO_VERSION_LEN                            = (2)
M1_PROTO_MAIN_TYPE_POS                          = (1 * 64 + 0 * 16 + 2)
M1_PROTO_MAIN_TYPE_LEN                          = (2)
M1_PROTO_SUB_TYPE_POS                           = (1 * 64 + 0 * 16 + 4)
M1_PROTO_SUB_TYPE_LEN                           = (2)
M1_PROTO_TRAY_POS                               = (1 * 64 + 0 * 16 + 6)
M1_PROTO_TRAY_LEN                               = (2)
M1_PROTO_COLOR_NUMS_POS                         = (1 * 64 + 0 * 16 + 8)
M1_PROTO_COLOR_NUMS_LEN                         = (1)
M1_PROTO_ALPHA_POS                              = (1 * 64 + 0 * 16 + 9)
M1_PROTO_ALPHA_LEN                              = (1)
M1_PROTO_RGB_1_POS                              = (1 * 64 + 1 * 16 + 0)
M1_PROTO_RGB_1_LEN                              = (3)
M1_PROTO_RGB_2_POS                              = (1 * 64 + 1 * 16 + 3)
M1_PROTO_RGB_2_LEN                              = (3)
M1_PROTO_RGB_3_POS                              = (1 * 64 + 1 * 16 + 6)
M1_PROTO_RGB_3_LEN                              = (3)
M1_PROTO_RGB_4_POS                              = (1 * 64 + 1 * 16 + 9)
M1_PROTO_RGB_4_LEN                              = (3)
M1_PROTO_RGB_5_POS                              = (1 * 64 + 1 * 16 + 12)
M1_PROTO_RGB_5_LEN                              = (3)
M1_PROTO_SKU_POS                                = (1 * 64 + 2 * 16 + 0)
M1_PROTO_SKU_LEN                                = (4)
# Section 2
M1_PROTO_DIAMETER_POS                           =( 2 * 64 + 0 * 16 + 0)
M1_PROTO_DIAMETER_LEN                           = (2)
M1_PROTO_WEIGHT_POS                             = (2 * 64 + 0 * 16 + 2)
M1_PROTO_WEIGHT_LEN                             = (2)
M1_PROTO_LENGTH_POS                             = (2 * 64 + 0 * 16 + 4)
M1_PROTO_LENGTH_LEN                             = (2)
M1_PROTO_DRY_TEMP_POS                           = (2 * 64 + 1 * 16 + 0)
M1_PROTO_DRY_TEMP_LEN                           = (2)
M1_PROTO_DRY_TIME_POS                           = (2 * 64 + 1 * 16 + 2)
M1_PROTO_DRY_TIME_LEN                           = (2)
M1_PROTO_HOTEND_MAX_TEMP_POS                    = (2 * 64 + 1 * 16 + 4)
M1_PROTO_HOTEND_MAX_TEMP_LEN                    = (2)
M1_PROTO_HOTEND_MIN_TEMP_POS                    = (2 * 64 + 1 * 16 + 6)
M1_PROTO_HOTEND_MIN_TEMP_LEN                    = (2)
M1_PROTO_BED_TYPE_POS                           = (2 * 64 + 1 * 16 + 8)
M1_PROTO_BED_TYPE_LEN                           = (2)
M1_PROTO_BED_TEMP_POS                           = (2 * 64 + 1 * 16 + 10)
M1_PROTO_BED_TEMP_LEN                           = (2)
M1_PROTO_FIRST_LAYER_TEMP_POS                   = (2 * 64 + 1 * 16 + 12)
M1_PROTO_FIRST_LAYER_TEMP_LEN                   = (2)
M1_PROTO_OTHER_LAYER_TEMP_POS                   = (2 * 64 + 1 * 16 + 14)
M1_PROTO_OTHER_LAYER_TEMP_LEN                   = (2)
M1_PROTO_MF_DATE_POS                            = (2 * 64 + 2 * 16 + 0)
M1_PROTO_MF_DATE_LEN                            = (8)
M1_PROTO_RSA_KEY_VER_POS                        = (2 * 64 + 2 * 16 + 8)
M1_PROTO_RSA_KEY_VER_LEN                        = 2

# ERROR CODE
FILAMENT_PROTO_OK                               = 0
FILAMENT_PROTO_ERR                              = -1
FILAMENT_PROTO_PARAMETER_ERR                    = -2
FILAMENT_PROTO_RSA_KEY_VER_ERR                  = -3
FILAMENT_PROTO_SIGN_CHECK_ERR                   = -4

FILAMENT_PROTO_RSA_PUBLIC_KEY_0 = b"""
-----BEGIN RSA PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA8oEF7YuKO863TbUxnrvY
H1JFrvCnMapm8Ho952KlfNWbf6IEDMlX6QJpBuvUkrkjWpLJJQurIWL3KFeLUhCh
POrYdiGrdsUlp4YO037iLSlgmzo1dUdgbawAcGox1PvR/Naw5ADibubO2rN49WQR
+BkxxigvoWHSFetaoMCswQ5B/niq3byhzktgmWOcv71F4yFwcxivF8R+s0gSBL4i
/1zNeSUZkbvP4/T0B08i3D+e6fl9xpCnINZ3P9OWcx+p3SB2o4TdmAeKV4hkT9n7
o+/OWr92fx6qbiNKJr04oMhrRsFK6w7hitp2n8RGS64w9lhtplnBgxtbgxAYyUnp
qwIDAQAB
-----END RSA PUBLIC KEY-----"""

FILAMENT_PROTO_RSA_PUBLIC_KEY_1 = b"""
-----BEGIN RSA PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA8nbtQNABbc5PkyzI0A5m
VH/E8y23Wld0iykvTOoBYJOrPwJDmXsnSyyX84Nv6voSr8FYv3Fb2SqSdOgQLFqp
BXvntXew8rPpq5Ll8gSzLRxE1VmEOVtZWCTJ4Wxwwi79rrFmpa/nAtUeYZIGiiud
w2MzCHXW5G3c1FWhQ0C8vUUMfBQXmGnoHGsul6R8xld6CDCWY8ia/FvfR+KCtMRn
VYyYguYsq4rODWJHiFCOef4FZconUR3RTh0ojvq78CsHk94goxidWzZoKcVnvWhh
bOixTjU37W4JDECEOui3ObMMvJkzxkZo1irlAH7jTiPqhP94U/JbRDpBlHOOn67b
GQIDAQAB
-----END RSA PUBLIC KEY-----"""

FILAMENT_PROTO_RSA_PUBLIC_KEY_2 = b"""
-----BEGIN RSA PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAxZQPYewwMFaPlcEHq+SH
QS1C1NhVmAaY56qxLyHJ4aNc2iWdCx4/9ZKY4CL6xkeCD88Zndv/xzImplRdoAzo
whD47Vm4iuq8+NqHUI8na6ISd+MZ/O6/eo/ggaEZBX8lR+Yf0qfWtntsI9flUOoJ
mq1IXvNXqOxflUmPyffT40QSkAN4Rr3scB3ozlxuJZehWM/lUmZ1H5PQDwAqsM0T
Rj6ChzVmUbSvwEvbDTwpXkpMA0C5//OW0T//IKDEBYxEl928vYbraLRDRIetgdaD
o+77+ztfOv4AyP/ipikprHwIWi7yga5KUXq/XpNPy6cPISZD+/LBUJBxLELspREP
rQIDAQAB
-----END RSA PUBLIC KEY-----"""

FILAMENT_PROTO_RSA_PUBLIC_KEY_3 = b"""
-----BEGIN RSA PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvK8cJyeFeTkFgkSLCCAg
EgR9KAvIHmvK8CRdtn+W6PiIbN04MFIg8jiYW/3fq+AcBFFMo+HtR2gym8JNVx2I
RDI4WdfbR/0gaIHjOQ41OwlXmqqSkDsFmjxVI6bDRZYpHkOfkC+9Vi1Aii4l/Yq9
O7s+2j4zP9GoUWWJPb3mW07Vu+EnHB/XIuaoDJVQAS+ov3xTotCeKdcdgySnNP5g
kOvWUvWtwNQldCRcQ0eo3j5RO+4J4IRK2J8q7BrdV/gbJUE/BBPIOuURPLzNJJO3
wgx4PEwlb5uYEUL35ARL7NzL8ZOxebzs5H4tXuWrBhALw6O33Tfg3TmTmwR2JUpv
7QIDAQAB
-----END RSA PUBLIC KEY-----"""

FILAMENT_PROTO_RSA_PUBLIC_KEY_4 = b"""
-----BEGIN RSA PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvafhk7Bdb3F+5B9w7YXv
chrNzl09QkZc27NLxL0ViRitGQhX9KC/xVg+XkBGI8XfioAwYkJ3jYgwmci5gJOL
ofPyNXcFtvtzq2NZNuDZY26krrXLORhS1o8ue92RB2gM92Rc2heWVrsvLycNl2Qz
OUjUEGmWpSMo98xIsgkTZJ4aYxWVN86yqknOcHVpTmcr5SBRB90K9hTRtsaMD97O
FYVc7AA/TGwqFJOnXXzWczWtg7kUY2vqCHwsvKs3G/EIFKOIe1n37V94OcxHTySC
co9Kc6Y0bGFIwIruinH1WkFVt6TAzo+0ZdZy5Sq493AG9y1RZ5nYj5qUmc1PMmrD
gwIDAQAB
-----END RSA PUBLIC KEY-----"""

FILAMENT_PROTO_RSA_PUBLIC_KEY_5 = b"""
-----BEGIN RSA PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAxWdxd7qeouSFbZ2Sldv3
apDrgAupOYiDRkO85C+qkZaezOzqW0EsOV0x7nG/smw++TRfHyGIK4gXCdg1JfNR
WYjqckRdnLYMzGdDk24VV5Bbrsgska0v0Oy1ucz3CYu+F22ais00OqK0MY0B96MI
/B/0pRSTAIyxvC6LjhHy8DYyPdqNF9EMikKfAfcn7ytsH1PoSSGVtrZqyNe5OLrW
yAw+FQsTg/VFJcYxPTQJ1ymwQmDCdKgApe3PVajyYswoIA7R0S8ujau0aAFEO3dU
GDEwjOnaHfwFlg3OKMFJTxc2sl/WEB8xtWuKl0Guf0VnzWJ6noxqf/DiaN1fuHG0
AwIDAQAB
-----END RSA PUBLIC KEY-----"""

FILAMENT_PROTO_RSA_PUBLIC_KEY_6 = b"""
-----BEGIN RSA PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqF+YJNHLHC6c25oTDgNg
liahUxWBPSkgght1/gJu5vBRDKWEn6i/RuKAFdTOsH+Hlvr5qWms7bBUHx78UMF+
FF1Nq9tb4jhFuqq4HWsBBjNnU6O0JhFTjKJU2nudmphXlpdLQfcKSIYMQe795GHL
izh8WsNTcTHNNBkjhi7y4c4RUqnJso0L6vrf0B3EB/9DDUJitrwfw+1/OrKOEVEP
624sEa802cHfb+BG9zKBXjFwzYCYF9gWey9yeA3UA7EYmPpqA1lqNv8m0r7YjZ4n
uGBDjs+AXaGtdqrW3IUtkUF2vWwNSRncbcXi3mNfzslrtPhsDVAFki4vDSw7yNht
2wIDAQAB
-----END RSA PUBLIC KEY-----"""

FILAMENT_PROTO_RSA_PUBLIC_KEY_7 = b"""
-----BEGIN RSA PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuKWRCTTgxPltfflWHdhu
2ITxWC/LTEl7OtatNWFhMFQZF2J5SN/45bjH6xIPTcDglTSl2/UMC1D/ugiq+j0z
dGSdE7xn3ZSzLTMCwgRkvXmd8aQgafBYbB7E6oAgus+6lRXZPwnMfZAe0yaJNHyt
1Wd8ZUlRY7BHSPPtmG1liVEzxoTb6urB6mK49r24+oC7xa65q5NSdlZWSTeaK4Xt
DVVDiwe+uubNTm59KnVAKgBMNd3qN942pH6fo/dBz++BzJVEG/qJewHUTGZAeIl+
CgqhSEbmEIgolsDgaKY99ZWa2FWJdo+ohYhmjc92TyB9kWw6yIwez+tlRUkssLGt
SwIDAQAB
-----END RSA PUBLIC KEY-----"""

FILAMENT_PROTO_RSA_PUBLIC_KEY_8 = b"""
-----BEGIN RSA PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAt7XOTs6P2xB8v8/xWVdR
wVefphRDXSuv74RObtr0pwLTc7BytkcDw8r60BNPv9hGDpW2S1szxqS8x4EaOHP7
81qNpIUULlUdXxty1RvpSdfRb044kpwl7A/s4OEakkyJZF1ed+Qte1FqOFDDIZ+l
g+Co8FjOwWixoSyIlR22mEP7r6Y98GL5tnSohkVoGAgEipswWb6549mssjZmES+J
hB0axY6Dl/LlDYxN6jjUZwSIo7bw0GXGm9ScW2qTVaT1m2A9etpD6OIG+iQVLQqP
whVBs5q0o/EM4nBN88RBsF2OmfkcZPJ2NdX6o3qx+pCZ9NDgkHjGDZdnGEnM5Lu2
dwIDAQAB
-----END RSA PUBLIC KEY-----"""

FILAMENT_PROTO_RSA_PUBLIC_KEY_9 = b"""
-----BEGIN RSA PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAz/d5C5FpqlcF7NbUEvBN
fiDJWH0BF63PEwHPiX+cS6l+q4NqqYI167u1pGkZGJV1njgGYFTM08x2KO7/bk6o
CWcGuKWNM8Tp1+tv3XioNGVCnIpHmdUx5F9qcXlPtDx74wQk/+JZLQ/sLnLvHcV3
YTaz55fpyzVUHkgXusdVynSyAt3ywWWQRcjp3sspGa/udC0j6LCvrzqLACv3gMGA
Id0b6REzjSn03UzkwBIwSb8DszieeNhaCOK4M/TxPFNyrhQRYcAvhiZJu+tylqJs
VP+gaWFvElFeFkxcHvYXHdJPlJLjYeT51hm/pdll26yYLhpeBa0inHwSqv4D3jFZ
PQIDAQAB
-----END RSA PUBLIC KEY-----"""


def get_key_by_value(dict_obj, value):
    for key, val in dict_obj.items():
        if val == value:
            return key
    return None

def verify_signature_pkcs1(public_key, data, signature):
    try:
        public_key = serialization.load_pem_public_key(public_key, backend=default_backend())
        public_key.verify(
            signature,
            data,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except InvalidSignature:
        return False

def m1_proto_data_parse(data_buf):
    if (None == data_buf or isinstance(data_buf, list) == False) or\
            len(data_buf) != M1_PROTO_TOTAL_SIZE:
        return FILAMENT_PROTO_PARAMETER_ERR, None

    rsa_ver = data_buf[M1_PROTO_RSA_KEY_VER_POS : M1_PROTO_RSA_KEY_VER_POS + M1_PROTO_RSA_KEY_VER_LEN]
    rsa_ver = (rsa_ver[1] << 8) | (rsa_ver[0])
    rsa_key_select = FILAMENT_PROTO_RSA_PUBLIC_KEY_0
    if rsa_ver == 0:
        rsa_key_select = FILAMENT_PROTO_RSA_PUBLIC_KEY_0
    elif rsa_ver == 1:
        rsa_key_select = FILAMENT_PROTO_RSA_PUBLIC_KEY_1
    elif rsa_ver == 2:
        rsa_key_select = FILAMENT_PROTO_RSA_PUBLIC_KEY_2
    elif rsa_ver == 3:
        rsa_key_select = FILAMENT_PROTO_RSA_PUBLIC_KEY_3
    elif rsa_ver == 4:
        rsa_key_select = FILAMENT_PROTO_RSA_PUBLIC_KEY_4
    elif rsa_ver == 5:
        rsa_key_select = FILAMENT_PROTO_RSA_PUBLIC_KEY_5
    elif rsa_ver == 6:
        rsa_key_select = FILAMENT_PROTO_RSA_PUBLIC_KEY_6
    elif rsa_ver == 7:
        rsa_key_select = FILAMENT_PROTO_RSA_PUBLIC_KEY_7
    elif rsa_ver == 8:
        rsa_key_select = FILAMENT_PROTO_RSA_PUBLIC_KEY_8
    elif rsa_ver == 9:
        rsa_key_select = FILAMENT_PROTO_RSA_PUBLIC_KEY_9
    else:
        return FILAMENT_PROTO_RSA_KEY_VER_ERR, None

    # check digital signature
    signature_read = []
    for i in range(6):
        signature_read += copy.copy(data_buf[(10 + i) * 64 : (10 + i) * 64 + 48])
    signature_read = bytes(signature_read)
    if (verify_signature_pkcs1(rsa_key_select,
                         bytes(data_buf[0:640]), signature_read[0:256]) == False):
        return FILAMENT_PROTO_SIGN_CHECK_ERR, None

    info = copy.copy(FILAMENT_INFO_STRUCT)
    info['RSA_KEY_VERSION'] = rsa_ver

    tmp = data_buf[M1_PROTO_VERSION_POS : M1_PROTO_VERSION_POS + M1_PROTO_VERSION_LEN]
    tmp = (tmp[1] << 8) | (tmp[0])
    info['VERSION'] = tmp

    tmp = data_buf[M1_PROTO_VENDOR_POS : M1_PROTO_VENDOR_POS + M1_PROTO_VENDOR_LEN]
    tmp = bytes(tmp).decode('ascii').rstrip('\x00')
    info['VENDOR'] = tmp

    tmp = data_buf[M1_PROTO_MANUFACTURER_POS : M1_PROTO_MANUFACTURER_POS + M1_PROTO_MANUFACTURER_LEN]
    tmp = bytes(tmp).decode('ascii').rstrip('\x00')
    info['MANUFACTURER'] = tmp

    tmp = data_buf[M1_PROTO_MAIN_TYPE_POS : M1_PROTO_MAIN_TYPE_POS + M1_PROTO_MAIN_TYPE_LEN]
    tmp = (tmp[1] << 8) | (tmp[0])
    ret = get_key_by_value(FILAMENT_PROTO_MAIN_TYPE_MAPPING, tmp)
    if (ret == None):
        return FILAMENT_PROTO_ERR, None
    else:
        info['MAIN_TYPE'] = ret

    tmp = data_buf[M1_PROTO_SUB_TYPE_POS : M1_PROTO_SUB_TYPE_POS + M1_PROTO_SUB_TYPE_LEN]
    tmp = (tmp[1] << 8) | (tmp[0])
    ret = get_key_by_value(FILAMENT_PROTO_SUB_TYPE_MAPPING, tmp)
    if (ret == None):
        return FILAMENT_PROTO_ERR, None
    else:
        info['SUB_TYPE'] = ret

    tmp = data_buf[M1_PROTO_TRAY_POS : M1_PROTO_TRAY_POS + M1_PROTO_TRAY_LEN]
    tmp = (tmp[1] << 8) | (tmp[0])
    info['TRAY'] = tmp

    info['ALPHA'] = 0xFF - data_buf[M1_PROTO_ALPHA_POS]

    tmp = data_buf[M1_PROTO_COLOR_NUMS_POS]
    if tmp > FILAMENT_PROTO_COLOR_NUMS_MAX :
        return FILAMENT_PROTO_ERR, None
    info['COLOR_NUMS'] = tmp

    tmp = data_buf[M1_PROTO_RGB_1_POS : M1_PROTO_RGB_1_POS + M1_PROTO_RGB_1_LEN]
    tmp = (tmp[0] << 16) | (tmp[1] << 8) | (tmp[2])
    info['RGB_1'] = tmp
    tmp = data_buf[M1_PROTO_RGB_2_POS : M1_PROTO_RGB_2_POS + M1_PROTO_RGB_2_LEN]
    tmp = (tmp[0] << 16) | (tmp[1] << 8) | (tmp[2])
    info['RGB_2'] = tmp
    tmp = data_buf[M1_PROTO_RGB_3_POS : M1_PROTO_RGB_3_POS + M1_PROTO_RGB_3_LEN]
    tmp = (tmp[0] << 16) | (tmp[1] << 8) | (tmp[2])
    info['RGB_3'] = tmp
    tmp = data_buf[M1_PROTO_RGB_4_POS : M1_PROTO_RGB_4_POS + M1_PROTO_RGB_4_LEN]
    tmp = (tmp[0] << 16) | (tmp[1] << 8) | (tmp[2])
    info['RGB_4'] = tmp
    tmp = data_buf[M1_PROTO_RGB_5_POS : M1_PROTO_RGB_5_POS + M1_PROTO_RGB_5_LEN]
    tmp = (tmp[0] << 16) | (tmp[1] << 8) | (tmp[2])
    info['RGB_5'] = tmp
    info['ARGB_COLOR'] = info['ALPHA'] << 24 | info['RGB_1']

    tmp = data_buf[M1_PROTO_DIAMETER_POS : M1_PROTO_DIAMETER_POS + M1_PROTO_DIAMETER_LEN]
    tmp = (tmp[1] << 8) | (tmp[0])
    info['DIAMETER'] = tmp

    tmp = data_buf[M1_PROTO_WEIGHT_POS : M1_PROTO_WEIGHT_POS + M1_PROTO_WEIGHT_LEN]
    tmp = (tmp[1] << 8) | (tmp[0])
    info['WEIGHT'] = tmp

    tmp = data_buf[M1_PROTO_LENGTH_POS : M1_PROTO_LENGTH_POS + M1_PROTO_LENGTH_LEN]
    tmp = (tmp[1] << 8) | (tmp[0])
    info['LENGTH'] = tmp

    tmp = data_buf[M1_PROTO_DRY_TEMP_POS : M1_PROTO_DRY_TEMP_POS + M1_PROTO_DRY_TEMP_LEN]
    tmp = (tmp[1] << 8) | (tmp[0])
    info['DRYING_TEMP'] = tmp

    tmp = data_buf[M1_PROTO_DRY_TIME_POS : M1_PROTO_DRY_TIME_POS + M1_PROTO_DRY_TIME_LEN]
    tmp = (tmp[1] << 8) | (tmp[0])
    info['DRYING_TIME'] = tmp

    tmp = data_buf[M1_PROTO_HOTEND_MAX_TEMP_POS : M1_PROTO_HOTEND_MAX_TEMP_POS + M1_PROTO_HOTEND_MAX_TEMP_LEN]
    tmp = (tmp[1] << 8) | (tmp[0])
    info['HOTEND_MAX_TEMP'] = tmp

    tmp = data_buf[M1_PROTO_HOTEND_MIN_TEMP_POS : M1_PROTO_HOTEND_MIN_TEMP_POS + M1_PROTO_HOTEND_MIN_TEMP_LEN]
    tmp = (tmp[1] << 8) | (tmp[0])
    info['HOTEND_MIN_TEMP'] = tmp

    tmp = data_buf[M1_PROTO_BED_TYPE_POS : M1_PROTO_BED_TYPE_POS + M1_PROTO_BED_TYPE_LEN]
    tmp = (tmp[1] << 8) | (tmp[0])
    info['BED_TYPE'] = tmp

    tmp = data_buf[M1_PROTO_BED_TEMP_POS : M1_PROTO_BED_TEMP_POS + M1_PROTO_BED_TEMP_LEN]
    tmp = (tmp[1] << 8) | (tmp[0])
    info['BED_TEMP'] = tmp

    tmp = data_buf[M1_PROTO_FIRST_LAYER_TEMP_POS : M1_PROTO_FIRST_LAYER_TEMP_POS + M1_PROTO_FIRST_LAYER_TEMP_LEN]
    tmp = (tmp[1] << 8) | (tmp[0])
    info['FIRST_LAYER_TEMP'] = tmp

    tmp = data_buf[M1_PROTO_OTHER_LAYER_TEMP_POS : M1_PROTO_OTHER_LAYER_TEMP_POS + M1_PROTO_OTHER_LAYER_TEMP_LEN]
    tmp = (tmp[1] << 8) | (tmp[0])
    info['OTHER_LAYER_TEMP'] = tmp

    tmp = data_buf[M1_PROTO_SKU_POS : M1_PROTO_SKU_POS + M1_PROTO_SKU_LEN]
    info['SKU'] = (tmp[3] << 24) | (tmp[2] << 16) | (tmp[1] << 8) | (tmp[0] << 0)

    info['CARD_UID'] = data_buf[M1_PROTO_UID_POS : M1_PROTO_UID_POS + M1_PROTO_UID_LEN]

    info['OFFICIAL'] = True

    return FILAMENT_PROTO_OK, info

def ntag_ndef_data_parse(data_buf):
    """Parse NTAG215/216 user memory containing an NDEF Text Record.

    Expected NDEF text payload format: MATERIAL#RRGGBB
    Example: PLA#FF5733

    Args:
        data_buf: list of ints, raw bytes from NTAG page 4 onward

    Returns:
        (FILAMENT_PROTO_OK, info_dict) on success
        (FILAMENT_PROTO_ERR, None) on parse failure
    """
    if data_buf is None or not isinstance(data_buf, list) or len(data_buf) < 16:
        return FILAMENT_PROTO_PARAMETER_ERR, None

    try:
        # Find NDEF Message TLV (type=0x03) in TLV block
        offset = 0
        ndef_data = None
        while offset < len(data_buf) - 1:
            tlv_type = data_buf[offset]
            if tlv_type == 0x00:
                # NULL TLV, skip
                offset += 1
                continue
            if tlv_type == 0xFE:
                # Terminator TLV
                break
            if offset + 1 >= len(data_buf):
                break
            tlv_len = data_buf[offset + 1]
            if tlv_len == 0xFF:
                # 3-byte length format
                if offset + 3 >= len(data_buf):
                    break
                tlv_len = (data_buf[offset + 2] << 8) | data_buf[offset + 3]
                tlv_value_start = offset + 4
            else:
                tlv_value_start = offset + 2

            if tlv_type == 0x03:
                # NDEF Message TLV found
                tlv_value_end = tlv_value_start + tlv_len
                if tlv_value_end > len(data_buf):
                    return FILAMENT_PROTO_ERR, None
                ndef_data = data_buf[tlv_value_start:tlv_value_end]
                break

            # Skip unknown TLV
            offset = tlv_value_start + tlv_len

        if ndef_data is None or len(ndef_data) < 3:
            return FILAMENT_PROTO_ERR, None

        # Parse NDEF Record header
        header = ndef_data[0]
        tnf = header & 0x07
        type_len = ndef_data[1]
        # Short Record (SR) bit check
        if header & 0x10:
            payload_len = ndef_data[2]
            rec_type_start = 3
        else:
            if len(ndef_data) < 6:
                return FILAMENT_PROTO_ERR, None
            payload_len = ((ndef_data[2] << 24) | (ndef_data[3] << 16) |
                           (ndef_data[4] << 8) | ndef_data[5])
            rec_type_start = 6

        rec_type = ndef_data[rec_type_start:rec_type_start + type_len]
        payload_start = rec_type_start + type_len
        payload = ndef_data[payload_start:payload_start + payload_len]

        # Verify: TNF=0x01 (NFC Forum well-known type), Type="T" (Text)
        if tnf != 0x01 or rec_type != [ord('T')]:
            return FILAMENT_PROTO_ERR, None

        if len(payload) < 1:
            return FILAMENT_PROTO_ERR, None

        # Text Record: first byte = status (bit 7=encoding, bits 5-0=lang code len)
        lang_code_len = payload[0] & 0x3F
        text_start = 1 + lang_code_len
        if text_start >= len(payload):
            return FILAMENT_PROTO_ERR, None

        text_bytes = payload[text_start:]
        text = bytes(text_bytes).decode('utf-8').strip()

        # Parse MATERIAL#RRGGBB
        if '#' not in text:
            return FILAMENT_PROTO_ERR, None

        parts = text.split('#', 1)
        material_type = parts[0].upper().strip()
        color_hex = parts[1].strip()

        if material_type not in NTAG_SUPPORTED_MATERIAL_TYPES:
            return FILAMENT_PROTO_ERR, None

        if len(color_hex) != 6:
            return FILAMENT_PROTO_ERR, None

        rgb_value = int(color_hex, 16)

    except (IndexError, ValueError, UnicodeDecodeError):
        return FILAMENT_PROTO_ERR, None

    info = copy.copy(FILAMENT_INFO_STRUCT)
    info['VENDOR'] = 'Generic'
    info['MAIN_TYPE'] = material_type
    info['SUB_TYPE'] = 'Basic'
    info['COLOR_NUMS'] = 1
    info['ALPHA'] = 0xFF
    info['RGB_1'] = rgb_value
    info['ARGB_COLOR'] = 0xFF000000 | rgb_value
    info['OFFICIAL'] = False

    return FILAMENT_PROTO_OK, info

