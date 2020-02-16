import os
import json
import surfex
from surfex.util import error, data_merge
import copy
import shutil
import subprocess
from abc import ABC, abstractmethod, ABCMeta
import numpy as np
try:
    from StringIO import StringIO   # Python 2.x
except ImportError:
    from io import StringIO         # Python 3.x


class InputFieldData(object):
    __metaclass__ = ABCMeta

    def __init__(self, geo, var_name):
        self.geo_out = geo
        self.var_name = var_name
        # print "Constructed "+self.__class__.__name__+" for " + self.var_name

    @abstractmethod
    def read_time_step(self, validtime, cache):
        raise NotImplementedError('users must define read_time_step to use this base class')

    @abstractmethod
    def print_info(self):
        raise NotImplementedError('users must define read_time_step to use this base class')


# Direct data can be ead with this class with converter = None
class ConvertedInput(InputFieldData):

    def __init__(self, geo, var_name, converter):
        InputFieldData.__init__(self, geo, var_name)
        self.geo_out = geo
        self.var_name = var_name
        self.converter = converter

    def read_time_step(self, validtime, cache):
        field = self.converter.read_time_step(self.geo_out, validtime, cache)
        # Preserve positive values for precipitation
        if self.var_name == "RAIN" or self.var_name == "SNOW":
            field[field < 0.] = 0.
        return field

    def print_info(self):
        print(self.var_name)
        self.converter.print_info()


class ConstantValue(InputFieldData):

    def __init__(self, geo, var_name, var_dict):
        InputFieldData.__init__(self, geo, var_name)
        self.geo_out = geo
        self.var_name = var_name
        self.var_dict = var_dict
        if "value" in self.var_dict:
            self.value = self.var_dict["value"]
        else:
            print("Constant value must have a value!")
            raise

    def read_time_step(self, validtime, cache):
        field = np.array([float(i) for i in range(0, self.geo_out.npoints)])
        field.fill(self.value)
        # print field.shape
        return field

    def print_info(self):
        print(self.var_name)


def remove_existing_file(f_in, f_out):
    print(f_in, f_out)
    if f_in is None:
        raise FileNotFoundError("Input file not set")
    # If files are not the same file
    if os.path.abspath(f_in) != os.path.abspath(f_out):
        # print("trygve", f_out)
        if os.path.isdir(f_out):
            raise IsADirectoryError(f_out + " is a directory! Please remove it if desired")
        if os.path.islink(f_out):
            os.unlink(f_out)
        if os.path.isfile(f_out):
            os.remove(f_out)
    # files have the same path. Remove if it is a symlink
    else:
        if os.path.islink(f_out):
            os.unlink(f_out)


def create_working_dir(workdir):
    # Create work directory
    if workdir is not None:
        if os.path.isdir(workdir):
            shutil.rmtree(workdir)
        os.makedirs(workdir, exist_ok=True)
        os.chdir(workdir)


def clean_working_dir(workdir):
    # Clean up
    shutil.rmtree(workdir)


class InputData(ABC):

    def __init__(self):
        pass

    @abstractmethod
    def prepare_input(self):
        return NotImplementedError


class OutputData(ABC):

    def __init__(self):
        pass

    @abstractmethod
    def archive_files(self):
        return NotImplementedError


class JsonOutputData(OutputData):
    def __init__(self, data):
        OutputData.__init__(self)
        self.data = data

    def archive_files(self):
        for output_file, target in self.data.items():

            print(output_file, target)
            command = "mv"
            if type(target) is dict:
                for key in target:
                    print(output_file, key, target[key])
                    command = target[key]
                    target = key

            cmd = command + " " + output_file + " " + target
            try:
                print(cmd)
                subprocess.check_call(cmd, shell=True)
            except IOError:
                print(cmd + " failed")
                raise


class JsonOutputDataFromFile(JsonOutputData):
    def __init__(self, file):
        JsonOutputData.__init__(self, json.load(open(file, "r")))

    def archive_files(self):
        JsonOutputData.archive_files(self)


class JsonInputData(InputData):
    def __init__(self, data):
        InputData.__init__(self)
        self.data = data

    def prepare_input(self):
        for target, input_file in self.data.items():

            print(target, input_file)
            command = "ln -sf"
            if type(input_file) is dict:
                for key in input_file:
                    print(key, input_file[key])
                    command = str(input_file[key])
                    input_file = str(key)

            cmd = command + " " + input_file + " " + target
            try:
                print(cmd)
                subprocess.check_call(cmd, shell=True)
            except IOError:
                print(cmd + " failed")
                raise


class JsonInputDataFromFile(JsonInputData):
    def __init__(self, file):
        JsonInputData.__init__(self, json.load(open(file, "r")))

    def prepare_input(self):
        JsonInputData.prepare_input(self)


class Converter:
    """
    Main interface to read a field is done through a converter
    The converter is default "None" to read a plain field
    """

    def __init__(self, name, validtime, defs, conf, fileformat, basetime, intervall, debug):
        """
        Initializing the converter

        :param name: name
        :param conf: dictionary
        :param fileformat: format
        """

        self.name = name
        self.validtime = validtime
        self.basetime = basetime
        self.intervall = intervall

        if self.name == "none":
            self.var = self.create_variable(fileformat, defs, conf[self.name], debug)
        elif name == "rh2q":
            self.rh = self.create_variable(fileformat, defs, conf[self.name]["rh"], debug)
            self.t = self.create_variable(fileformat, defs, conf[self.name]["t"], debug)
            self.p = self.create_variable(fileformat, defs, conf[self.name]["p"], debug)
        elif name == "windspeed" or name == "winddir":
            self.x = self.create_variable(fileformat, defs, conf[self.name]["x"], debug)
            self.y = self.create_variable(fileformat, defs, conf[self.name]["y"], debug, need_alpha=True)
        elif name == "totalprec":
            self.totalprec = self.create_variable(fileformat, defs, conf[self.name]["totalprec"], debug)
            self.snow = self.create_variable(fileformat, defs, conf[self.name]["snow"], debug)
        elif name == "calcsnow":
            self.totalprec = self.create_variable(fileformat, defs, conf[self.name]["totalprec"], debug)
            self.t = self.create_variable(fileformat, defs, conf[self.name]["t"], debug)
        #            self.rh = self.create_variable(fileformat,defs,conf[self.name]["t"],debug)
        #            self.p = self.create_variable(fileformat,defs,conf[self.name]["p"],debug)
        elif name == "calcrain":
            self.totalprec = self.create_variable(fileformat, defs, conf[self.name]["totalprec"], debug)
            self.t = self.create_variable(fileformat, defs, conf[self.name]["t"], debug)
        elif name == "phi2m":
            self.phi = self.create_variable(fileformat, defs, conf[self.name]["phi"], debug)
        else:
            error("Converter " + self.name + " not implemented")

        # print "Constructed the converter " + self.name

    def print_info(self):
        print(self.name)

    def create_variable(self, fileformat, defs, var_dict, debug, need_alpha=False):

        # Finally we can merge the variable with the default settings
        # Create deep copies not to inherit between variables
        defs = copy.deepcopy(defs)
        var_dict = copy.deepcopy(var_dict)
        merged_dict = data_merge(defs, var_dict)

        var = None
        if fileformat == "netcdf":
            var = surfex.variable.NetcdfVariable(merged_dict, self.basetime, self.validtime, self.intervall, debug,
                                                 need_alpha=need_alpha)
        elif fileformat == "grib":
            var = surfex.variable.GribVariable(merged_dict, self.basetime, self.validtime, self.intervall, debug,
                                               need_alpha=need_alpha)
        elif fileformat == "constant":
            error("Create variable for format " + fileformat + " not implemented!")
        else:
            error("Create variable for format " + fileformat + " not implemented!")

        # TODO: Put this under verbose flag and format printing
        # var.print_variable_info()
        return var

    def read_time_step(self, geo, validtime, cache):
        # print("Time in converter: "+self.name+" "+validtime.strftime('%Y%m%d%H'))

        gravity = 9.81
        field = np.empty(geo.npoints)
        # Specific reading for each converter
        if self.name == "none":
            field = self.var.read_variable(geo, validtime, cache)
        elif self.name == "windspeed" or self.name == "winddir":
            field_x = self.x.read_variable(geo, validtime, cache)
            alpha, field_y = self.y.read_variable(geo, validtime, cache)
            # field_y = self.y.read_variable(geo,validtime,cache)
            if self.name == "windspeed":
                field = np.sqrt(np.square(field_x) + np.square(field_y))
                np.where(field < 0.005, field, 0)
            elif self.name == "winddir":
                field = np.mod(np.rad2deg(np.arctan2(field_x, field_y)) + 180 - alpha, 360)

        elif self.name == "rh2q":
            field_rh = self.rh.read_variable(geo, validtime, cache)  # %
            field_t = self.t.read_variable(geo, validtime, cache)  # In K
            field_p = self.p.read_variable(geo, validtime, cache)  # In Pa

            field_p_mb = np.divide(field_p, 100.)
            field_t_c = np.subtract(field_t, 273.15)

            exp = np.divide(np.multiply(17.67, field_t_c), np.add(field_t_c, 243.5))
            es = np.multiply(6.112, np.exp(exp))
            field = np.divide(np.multiply(0.622, field_rh / 100.) * es, field_p_mb)

            # ZES = 6.112 * exp((17.67 * (ZT - 273.15)) / ((ZT - 273.15) + 243.5))
            # ZE = ZRH * ZES
            # ZRATIO = 0.622 * ZE / (ZPRES / 100.)
            # RH2Q = 1. / (1. / ZRATIO + 1.)
        elif self.name == "totalprec":
            field_totalprec = self.totalprec.read_variable(geo, validtime, cache)
            field_snow = self.snow.read_variable(geo, validtime, cache)
            field = np.subtract(field_totalprec, field_snow)
        elif self.name == "calcrain":
            field_totalprec = self.totalprec.read_variable(geo, validtime, cache)
            field_t = self.t.read_variable(geo, validtime, cache)
            field = field_totalprec
            field[field_t < 1] = 0
        elif self.name == "calcsnow":
            field_totalprec = self.totalprec.read_variable(geo, validtime, cache)
            # field_rh = self.rh.read_variable(geo, validtime,cache) #
            field_t = self.t.read_variable(geo, validtime, cache)  # In K
            # field_p = self.p.read_variable(geo, validtime,cache)   # In Pa
            # tc = field_t + 273.15
            # e  = (field_rh)*0.611*exp((17.63*tc)/(tc+243.04));
            # Td = (116.9 + 243.04*log(e))/(16.78-log(e));
            # gamma = 0.00066 * field_p/1000;
            # delta = (4098*e)/pow(Td+243.04,2);
            # if(gamma + delta == 0):
            # print("problem?")
            # wetbulbTemperature = (gamma * tc + delta * Td)/(gamma + delta);
            # wetbulbTemperatureK  = wetbulbTemperature + 273.15;
            field = field_totalprec
            field[field_t > 1] = 0
        elif self.name == "phi2m":
            field = self.phi.read_variable(geo, validtime, cache)
            field = np.divide(field, gravity)
            field[(field < 0)] = 0.
        else:
            error("Converter " + self.name + " not implemented")
        return field
