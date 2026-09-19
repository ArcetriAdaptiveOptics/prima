#!/usr/bin/env python3
#
import dao
import daoEkarusShmNames as shm_names

ref = dao.shm(shm_names.SHM_OCAM_REFERENCE)
ref.set_data(ref.get_data() * 0)

refFlux = dao.shm(shm_names.SHM_OCAM_REFERENCE_FLUX)
refFlux.set_data(refFlux.get_data()*0 + 1.0)
