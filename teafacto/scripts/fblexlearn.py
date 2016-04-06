from teafacto.core.base import tensorops as T
from teafacto.core.base import Block
from teafacto.core.datafeed import DataFeed
from teafacto.blocks.basic import MatDot as Lin, Softmax
from teafacto.blocks.rnn import SeqEncoder
from teafacto.blocks.rnu import GRU
from teafacto.blocks.lang.wordembed import IdxToOneHot, WordEncoderPlusGlove, WordEmbedPlusGlove
from teafacto.blocks.lang.wordvec import Glove
from teafacto.util import argprun, ticktock, issequence
import numpy as np, pandas as pd
from IPython import embed


class FBBasicCompositeEncoder(Block):    # SeqEncoder of WordEncoderPlusGlove, fed to single-layer Softmax output
    def __init__(self, wordembdim=50, wordencdim=100, innerdim=200, outdim=1e4, numwords=4e5, numchars=128, **kw):
        super(FBBasicCompositeEncoder, self).__init__(**kw)
        self.indim = wordembdim + wordencdim
        self.outdim = outdim
        self.wordembdim = wordembdim
        self.wordencdim = wordencdim
        self.innerdim = innerdim

        self.enc = SeqEncoder(
            WordEncoderPlusGlove(numchars=numchars, numwords=numwords, encdim=self.wordencdim, embdim=self.wordembdim, embtrainfrac=0.0),
            GRU(dim=self.wordembdim + self.wordencdim, innerdim=self.innerdim)
        )

        self.out = Lin(indim=self.innerdim, dim=self.outdim)

    def apply(self, inp):
        enco = self.enc(inp)
        ret = Softmax()(self.out(enco))
        return ret


class FBLexDataFeed(DataFeed):
    def __init__(self, data, worddic, unkwordid=1, numwords=10, numchars=30, **kw):
        super(FBLexDataFeed, self).__init__(data, **kw)
        self.worddic = worddic
        self._shape = (data.shape[0], numwords, numchars+1)
        self.unkwordid = unkwordid

    @property
    def dtype(self):
        return np.dtype("int32")

    @property
    def ndim(self):
        return len(self._shape)

    @property
    def shape(self):
        return self._shape

    def __getitem__(self, item):
        ret = self.data.__getitem__(item)
        return self.transform(ret)

    def transform(self, x):
        def transinner(word):
            skip = False
            if word is None:
                retword = [0]*(self.shape[2]+1)         # missing word ==> all zeros
                skip = True
            else:
                if word in self.worddic:
                    retword = [self.worddic[word]]      # get word index
                else:
                    retword = [self.unkwordid]                       # unknown word
                retword.extend(map(ord, word))
                retword.extend([0]*(self.shape[2]-len(retword)+1))
            return retword, skip #np.asarray(retword, dtype="int32")
        '''print x, type(x), x.dtype, x.shape
        ret = np.zeros((x.shape + (self.shape[1], self.shape[2]+1)))
        retv = np.vectorize(transinner)(x)
        print retv
        for i in range(self.shape[2]):
            ret[..., i] = np.vectorize(lambda z: transinner(z))(x)[i]
        return ret'''

        #print type(x), x.dtype
        ret = np.zeros((x.shape[0], self.shape[1], self.shape[2]+1), dtype="int32")
        i = 0
        while i < x.shape[0]:
            j = 0
            while j < x.shape[1]:
                word = x[i, j]
                retword, skip = transinner(word)
                if skip:
                    j = x.shape[1]
                else:
                    ret[i, j, :] = retword
                j += 1
            i += 1
        return ret


class FBLexDataFeedsMaker(object):
    def __init__(self, datapath, worddic, entdic, numwords=10, numchars=30, unkwordid=1):
        self.path = datapath
        self.trainingdata = []
        self.golddata = []
        self.worddic = worddic
        self.numwords = numwords
        self.numchars = numchars
        self.unkwordid = unkwordid
        self.load(entdic)

    def load(self, entdic):
        self.trainingdata = []
        self.golddata = []
        tt = ticktock(self.__class__.__name__)
        tt.tick("loading freebase lex")
        with open(self.path) as f:
            c = 0
            for line in f:
                ns = line[:-1].split("\t")
                if len(ns) is not 2:
                    print line, c
                    continue
                sf, fb = ns
                self.trainingdata.append(self._process_sf(sf))
                self.golddata.append(entdic[fb])
                if c % 1e6 == 0:
                    tt.tock("%.0fM" % (c/1e6)).tick()
                c += 1
        self.golddata = np.asarray(self.golddata, dtype="int32")
        self.trainingdata = np.array(self.trainingdata)

    @property
    def trainfeed(self):
        return FBLexDataFeed(self.trainingdata, worddic=self.worddic, unkwordid=self.unkwordid, numwords=self.numwords, numchars=self.numchars)

    @property
    def goldfeed(self):
        return self.golddata    # already np array of int32

    def _process_sf(self, sf):
        words = sf.split(" ")
        if len(words) > self.numwords:
            words = words[:self.numwords]
        i = 0
        while i < len(words):
            if len(words[i]) > self.numchars:
                words[i] = words[i][:self.numchars]
            i += 1
        words.extend([None]*max(0, (self.numwords - len(words))))
        return words


def getglovedict(path, offset=2):
    gd = {}
    maxid = 0
    with open(path) as f:
        c = offset
        for line in f:
            ns = line.split(" ")
            w = ns[0]
            gd[w] = c
            maxid = max(maxid, c)
            c += 1
    return gd, maxid


def getentdict(path, offset=2):
    ed = {}
    maxid = 0
    with open(path) as f:
        for line in f:
            e, i = line[:-1].split("\t")
            ed[e] = int(i) + offset
            maxid = max(ed[e], maxid)
    return ed, maxid


def run(
        epochs=100,
        lr=1.,
        wreg=0.0001,
        numbats=100,
        fblexpath="/media/denis/My Passport/data/freebase/labelsrevlex.map.sample",
        glovepath="../../data/glove/glove.6B.50d.txt",
        fbentdicp="../../data/freebase/entdic.map",
        numwords=10,
        numchars=30,
        wordembdim=50,
        wordencdim=100,
        innerdim=300,
        wordoffset=1,
        validinter=5
    ):
    gd, vocnumwords = getglovedict(glovepath, offset=wordoffset)
    print gd["alias"]
    ed, vocnuments = getentdict(fbentdicp, offset=0)
    print ed["m.0ndj09y"]

    indata = FBLexDataFeedsMaker(fblexpath, gd, ed, numwords=numwords, numchars=numchars, unkwordid=wordoffset-1)
    datanuments = max(indata.goldfeed)+1
    tt = ticktock("fblextransrun")
    tt.tick()
    print "max entity id+1: %d" % datanuments
    print indata.trainfeed[0:9]
    tt.tock("transformed")
    #embed()

    traindata = indata.trainfeed
    golddata = indata.goldfeed

    # define model
    m = FBBasicCompositeEncoder(
        wordembdim=wordembdim,
        wordencdim=wordencdim,
        innerdim=innerdim,
        outdim=datanuments,
        numchars=128,               # ASCII
        numwords=vocnumwords,
    )

    #wenc = WordEncoderPlusGlove(numchars=numchars, numwords=vocnumwords, encdim=wordencdim, embdim=wordembdim)

    # train model   TODO
    m.train([traindata], golddata).adagrad(lr=lr).grad_total_norm(1.0).neg_log_prob()\
        .autovalidate().validinter(validinter).accuracy()\
        .train(numbats, epochs)
    #embed()
    tt.tick("predicting")
    print m.predict(traindata).shape
    tt.tock("predicted sample")


if __name__ == "__main__":
    argprun(run)