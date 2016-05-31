from teafacto.blocks.attention import Attention, LinearGateAttentionGenerator, WeightedSumAttCon
from teafacto.blocks.basic import VectorEmbed, IdxToOneHot
from teafacto.blocks.rnn import SeqTransducer, RecStack, SeqDecoder, BiRNU, SeqEncoder
from teafacto.blocks.rnu import GRU
from teafacto.core.base import Block, tensorops as T
from teafacto.util import issequence


class SeqEncDec(Block):
    def __init__(self, enc, dec, statetrans=None, **kw):
        super(SeqEncDec, self).__init__(**kw)
        self.enc = enc
        self.dec = dec
        if isinstance(statetrans, Block):
            self.statetrans = lambda x, y: statetrans(x)
        elif statetrans is True:
            self.statetrans = lambda x, y: x
        else:
            self.statetrans = statetrans

    def apply(self, inpseq, outseq, maskseq=None):
        enco, allenco = self.enc(inpseq, mask=maskseq)
        if self.statetrans is not None:
            topstate = self.statetrans(enco, allenco)
            deco = self.dec(allenco, outseq, mask=maskseq, initstates=[topstate])
        else:
            deco = self.dec(allenco, outseq, mask=maskseq)      # no state transfer
        return deco

    def get_init_info(self, inpseq, batsize, maskseq=None):
        enco, allenco = self.enc(inpseq, mask=maskseq)
        if self.statetrans is not None:
            topstate = self.statetrans(enco, allenco)
            initstates = [topstate]
        else:
            initstates = batsize
        return self.dec.get_init_info(allenco, None, initstates)

    def rec(self, x_t, *states):
        return self.dec.rec(x_t, *states)


class SeqEncDecAtt(SeqEncDec):
    def __init__(self, enclayers, declayers, attgen, attcon, decinnerdim, inconcat, outconcat, statetrans=None, **kw):
        enc = SeqEncoder(*enclayers).with_outputs.zeromask
        dec = SeqDecoder(
            declayers,
            attention=Attention(attgen, attcon),
            innerdim=decinnerdim,
            outconcat=outconcat,
            inconcat=inconcat
        )
        super(SeqEncDecAtt, self).__init__(enc, dec, statetrans=statetrans, **kw)


class SimpleSeqEncDecAtt(SeqEncDecAtt):
    def __init__(self,
                 inpvocsize=400,
                 inpembdim=None,
                 outvocsize=100,
                 outembdim=None,
                 encdim=100,
                 decdim=100,
                 attdim=100,
                 bidir=False,
                 rnu=GRU,
                 outconcat=True,
                 inconcat=True,
                 statetrans=None,
                 **kw):
        encinnerdim = [encdim] if not issequence(encdim) else encdim
        decinnerdim = [decdim] if not issequence(decdim) else decdim

        # encoder stack
        if inpembdim is None:
            inpemb = IdxToOneHot(inpvocsize)
            inpembdim = inpvocsize
        else:
            inpemb = VectorEmbed(indim=inpvocsize, dim=inpembdim)
        encrnus = []
        dims = [inpembdim] + encinnerdim
        i = 1
        while i < len(dims):
            if bidir:
                newrnu = BiRNU.fromrnu(rnu, dim=dims[i-1], innerdim=dims[i])
            else:
                newrnu = rnu(dim=dims[i-1], innerdim=dims[i])
            encrnus.append(newrnu)
            i += 1
        enclayers = [inpemb] + encrnus

        # attention
        attgen = LinearGateAttentionGenerator(indim=encinnerdim[-1] + decinnerdim[-1], attdim=attdim)
        attcon = WeightedSumAttCon()

        # decoder
        if outembdim is None:
            outemb = IdxToOneHot(outvocsize)
            outembdim = outvocsize
        else:
            outemb = VectorEmbed(indim=outvocsize, dim=outembdim)
        decrnus = []
        firstdecdim = outembdim if inconcat is False else outembdim + encinnerdim[-1]
        dims = [firstdecdim] + decinnerdim
        i = 1
        while i < len(dims):
            decrnus.append(rnu(dim=dims[i-1], innerdim=dims[i]))
            i += 1
        declayers = [outemb] + decrnus
        decinnerdim = encinnerdim[-1] if outconcat is False else encinnerdim[-1] + decinnerdim[-1]

        super(SimpleSeqEncDecAtt, self).__init__(enclayers, declayers, attgen, attcon, decinnerdim, inconcat, outconcat, statetrans=statetrans, **kw)